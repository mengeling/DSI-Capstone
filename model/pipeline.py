import numpy as np
import pandas as pd
from collections import defaultdict
from sklearn.preprocessing import StandardScaler
from sqlalchemy import create_engine

import constants as C


class Pipeline:
    def __init__(self):
        """
        Initialize pipeline by running all of the functions
        """
        self.y_mean = None
        self.d = defaultdict(list)
        self.scaler = StandardScaler()

    def fit_transform(self, df, y):
        """
        Fit and transform the training data
        """
        self.y_mean = y.mean()
        return self._run_pipeline(df, y)

    def transform(self, df):
        """
        Transform the test data
        """
        return self._run_pipeline(df)

    def transform_individual(self, df):
        """
        Transform a single reservation from the app demo
        """
        df = df.apply(pd.to_numeric, errors='ignore')
        df = self._create_date_features(df, individual=True)
        df = self._create_insurance_features(df, "Corporate", "Silvercar", "Personal")
        df = self._calculate_percent_cancelled(df)
        df = self._create_western_binary(df)
        df.replace({"Yes": 1, "No": 0, True: 1, False: 0}, inplace=True)
        return self.scaler.transform(df[C.MODEL_FEATURES_TO_KEEP])

    def _run_pipeline(self, df, y=None):
        """
        Make all of the requisite changes to the data frame
        """
        df = self._create_historical_features(df, y)
        df = self._create_date_features(df)
        df = self._create_binary_features(df)
        df.fillna(0, inplace=True)
        if y is not None:
            X = self.scaler.fit_transform(df.copy()[C.MODEL_FEATURES_TO_KEEP])
            return df, X
        X = self.scaler.transform(df.copy()[C.MODEL_FEATURES_TO_KEEP])
        return df, X

    def _create_date_features(self, df, individual=False):
        """
        Create all date-related features needed for the model
        """
        # Change columns to datetimes
        if individual:
            df[C.DATE_COLS_SHORT] = df[C.DATE_COLS_SHORT].apply(pd.to_datetime)
        else:
            df[C.DATE_COLS] = df[C.DATE_COLS].apply(self._change_datetimes)

        # Calculate the number of days between the created, pick-up, and drop-off columns
        df = self._calculate_time_between(df, individual,
                                          days_to_pickup=("pickup", "created_at"),
                                          trip_duration=("dropoff", "pickup"))

        # Create date binaries
        df["pickup_dow"] = df["pickup"].dt.dayofweek
        df["midday_pickup"] = df["pickup"].dt.hour.isin(np.arange(7, 13))
        df["weekend_pickup"] = df["pickup_dow"].isin([4, 5, 6]).astype(int)
        df["winter_pickup"] = df["pickup"].dt.month.isin([1, 12]).astype(int)
        return df

    @staticmethod
    def _change_datetimes(series):
        """
        Change timestamp columns from numbers to datetimes
        """
        return pd.to_datetime('1899-12-30') + pd.to_timedelta(series, 'D')

    @staticmethod
    def _calculate_time_between(df, individual, **kwargs):
        """
        Calculate the number of days between two datetime features
        """
        for k, (v1, v2) in kwargs.items():
            if individual:
                # Set the number of days to 0 if the app user chooses dates that don't make sense
                df[k] = 0 if df[v1].values < df[v2].values else (df[v1] - df[v2]).dt.total_seconds() / 86400
            else:
                df[k] = (df[v1] - df[v2]).dt.total_seconds() / 86400
        return df

    @staticmethod
    def _create_binary_features(df):
        """
        Create all binary features needed for the model
        """
        df["used_promo"] = df["promo_code_id"].notnull().astype(int)
        df["credit_card"] = df["postal_code"].notnull().astype(int)
        df["web_booking"] = (df["booking_application"] == "web").astype(int)
        df["western_pickup"] = (df["time_zone"] == "pst").astype(int)
        df["modified_profile"] = (df["updated_at"].dt.date > df["created_at_user"].dt.date).astype(int)
        return df

    def _create_historical_features(self, df, y):
        """
        Create all features related to user ride history
        """
        df["rides"] = self._get_past_ride_cnt(df, y)
        df["past_rides"] = df["rides"].apply(lambda lst: len(lst))
        df["past_cancellations"] = df["rides"].apply(lambda lst: sum(lst))
        df["past_percent_cancelled"] = df["past_cancellations"] / df["past_rides"]
        df["past_percent_cancelled"] = df["past_percent_cancelled"].fillna(self.y_mean)
        return df

    def _get_past_ride_cnt(self, df, y):
        """
        Iterate through user IDs to look up and append the user's past rides to the ride_history list. During training,
        the current reservation's label is added to the dictionary, so the result of the ride is recorded for the next
        time the user appears in the DataFrame. Returns the ride_history list to be added to the DataFrame.
        """
        ride_history = []
        for i, user_id in enumerate(df["user_id"]):
            ride_history.append(self.d[user_id].copy())
            if y is not None:
                self.d[user_id].append(y[i])
        return ride_history

    @staticmethod
    def _create_insurance_features(df, *args):
        """
        Create the three binary insurance features
        """
        for arg in args:
            col_name = "insurance_{}".format(arg.lower())
            df[col_name] = df["insurance"].iloc[0] == arg
        return df

    def _calculate_percent_cancelled(self, df):
        """
        Create the past_percent_cancelled and western_pickup features
        """
        df["past_rides"] = df["past_finished"] + df["past_cancellations"]
        if df["past_rides"].sum() == 0:
            df["past_percent_cancelled"] = self.y_mean
        else:
            df["past_percent_cancelled"] = df["past_cancellations"] / df["past_rides"]
        return df

    @staticmethod
    def _create_western_binary(df):
        """
        Create western_pickup binary feature
        """
        engine = create_engine(C.ENGINE)
        time_zone = engine.execute(C.GET_TIME_ZONE.format(df["location"].iloc[0])).fetchone()[0]
        df["western_pickup"] = time_zone == "pst"
        return df

    @staticmethod
    def _filter_data(df):
        """
        Filter out unnecessary columns and fill nulls
        """
        return df[C.MODEL_FEATURES_TO_KEEP].fillna(0)
