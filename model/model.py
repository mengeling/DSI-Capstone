import numpy as np
import pandas as pd
from sqlalchemy import create_engine
from collections import defaultdict
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score
from sklearn.model_selection import train_test_split
from sklearn.linear_model import LogisticRegression

import constants as C
from pipeline import Pipeline


class CancellationModel:
    def __init__(self, classifier):
        """
        Initialize model
        """
        self.X = None
        self.y = None
        self.pipeline = None
        self.d = None
        self.classifer = classifier

    def fit(self, df, y):
        """
        Transforms the training data and then fits the model
        """
        self.X = df
        self.y = y
        self.X, self.d = Pipeline()
        self.X = self.scaler.fit_transform(self.X.values)
        self.classifer.fit(self.X, self.y)

    def predict_proba(self, df):
        """
        Transforms the test data and then calculates probabilities
        """
        self.X = df
        self.pipeline = Pipeline(booked=True)
        self.X = self.scaler.transform(self.X.values)
        return self.classifer.predict_proba(self.X)[:, 1]

    def predict(self, df):
        """
        Calls predict_proba function and then makes predictions based off of the chosen threshold
        """
        return (self.predict_proba(df) > C.THRESHOLD).astype(int)

    def score(self, df, y):
        """
        Calculates the accuracy of the model's predictions
        """
        predictions = self.predict(df)
        print(predictions, y)
        return accuracy_score(y, self.predict(df))


def get_data(booked=False):
    """
    Query and join 6 tables from Postgres database to get all of the features needed for the model
    """
    engine = create_engine(C.ENGINE)
    df_reservations = pd.read_sql_query(C.BOOKED_RESERVATIONS if booked else C.PAST_RESERVATIONS, con=engine)
    df_users = pd.read_sql_query(C.USERS, con=engine)
    df_users = df_users[~df_users.index.duplicated(keep='first')]
    return df_reservations.join(df_users.set_index("id"), on="user_id", how="left")


if __name__ == '__main__':
    df = get_data()
    df["current_state"] = ((df["current_state"] != "finished") & (df["current_state"] != "started")).astype(int)
    y = df.pop("current_state").values
    X_train, X_test, y_train, y_test = train_test_split(df, y)
    model = CancellationModel(LogisticRegression())
    model.fit(X_train, y_train)
    print(model.score(X_test, y_test))
    df_booked = get_data(booked=True)
    print(np.sum(model.predict(df_booked.drop("current_state", axis=1))))
