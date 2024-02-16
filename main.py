#
# Copyright (C) Patrik Jonell and contributors 2021.
# Licensed under the MIT license. See LICENSE.txt file in the project root for details.
#

import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

from fastapi import FastAPI, Form, Query
from fastapi.staticfiles import StaticFiles
from pymongo import MongoClient
from starlette.responses import FileResponse, PlainTextResponse

app = FastAPI(docs_url=None, redoc_url=None)
app.mount("/prolific/lib", StaticFiles(directory="lib"), name="lib")
app.mount("/prolific/design", StaticFiles(directory="design"), name="design")


def connect_to_db():
    client = MongoClient(
        "mongodb://db:27017",
        username=os.environ["MONGO_USERNAME"],
        password=os.environ["MONGO_PASSWORD"],
    )
    return client.test_database


@app.get("/prolific/startup.js")
def startup():
    return FileResponse("startup.js")


@app.get("/configs/{test_id}/{user_id}")
def configs(test_id: str, user_id: str):
    status = connect_to_db().status.find_one(
        {"userId": user_id, "testId": test_id, "status": "ACTIVE"}
    )
    data = json.load(open(status["experiment_file"]))
    data["userId"] = user_id
    data["testId"] = test_id
    return data


@app.post("/fail")
def fail(user_id=Form(...), test_id=Form(...), sessionJSON=Form(...)):
    db = connect_to_db()

    data = json.loads(sessionJSON)
    ended_date = datetime.now()
    data["date"] = ended_date
    db.fail_responses.insert_one(data)

    if db.fail_responses.count_documents({"userId": user_id}) > 0:
        db.status.update(
            {"userId": user_id, "testId": test_id},
            {"$set": {"status": "FAILED", "ended": datetime.now()}},
        )
        return True
    else:
        return False


@app.get("/failed_task", response_class=PlainTextResponse)
def failed():
    return "Sorry, you have failed several attention checks. Even if you press back, and redo the study, your responses won't be registered."


@app.post("/partial")
def partial(
    ratings=Form(...),
    user_id=Form(...),
    test_id=Form(...),
    page_id=Form(...),
    interaction=Form(...),
    navigator=Form(...),
):
    data = {
        "modified": datetime.now(),
        "ratings": ratings,
        "user_id": user_id,
        "test_id": test_id,
        "page_id": page_id,
        "interaction": interaction,
        "navigator": navigator,
    }
    connect_to_db().partial_responses.insert_one(data)
    return {}

@app.post("/partial_questionnaire")
def partial_questionnaire(
    ratings=Form(...),
    user_id=Form(...),
    test_id=Form(...),
    page_id=Form(...),
    interaction=Form(...),
    navigator=Form(...),
    questionnaire=Form(...)
):
    data = {
        "modified": datetime.now(),
        "ratings": ratings,
        "user_id": user_id,
        "test_id": test_id,
        "page_id": page_id,
        "interaction": interaction,
        "navigator": navigator,
        "questionnaire": questionnaire,
    }
    connect_to_db().partial_responses.insert_one(data)
    return {}


@app.post("/save", response_class=PlainTextResponse)
def save(sessionJSON=Form(...)):
    data = json.loads(sessionJSON)
    db = connect_to_db()
    ended_date = datetime.now()
    data["ended"] = ended_date
    db.responses.insert_one(data)
    db.status.update(
        {"userId": data["userId"], "testId": data["testId"]},
        {"$set": {"status": "DONE", "ended": ended_date}},
    )
    code = db.codes.find_one({"testId": data["testId"]})
    return code["code"]


@app.get("/prolific/{test_id}")
def index(
    test_id: str, PROLIFIC_PID=Query(...), STUDY_ID=Query(...), SESSION_ID=Query(...)
):
    db = connect_to_db()

    db.status.remove(
        {"status": "ACTIVE", "date": {"$lt": datetime.now() - timedelta(minutes=100)}}
    )

    status = db.status.find_one({"userId": PROLIFIC_PID, "testId": test_id})

    if not status:
        blocked = db.status.find(
            {"status": {"$in": ["DONE", "ACTIVE"]}, "testId": test_id}
        )
        blocked_files = [x["experiment_file"] for x in blocked]

        config_path = Path("configs") / re.sub(r"\W+", "", test_id)
        potential_files = [
            x for x in sorted(config_path.glob("*.json")) if str(x) not in blocked_files
        ]
        if not potential_files:
            return PlainTextResponse("Sorry, you cannot do this experiment right now")

        db.status.insert(
            {
                "status": "ACTIVE",
                "experiment_file": str(potential_files[0]),
                "testId": test_id,
                "userId": PROLIFIC_PID,
                "studyId": STUDY_ID,
                "sessionId": SESSION_ID,
                "date": datetime.now(),
            }
        )

    elif status["status"] == "FAILED":
        return PlainTextResponse("Sorry, you cannot do this experiment anymore")
    elif status["status"] == "DONE":
        return PlainTextResponse(
            "Sorry, it seems like you have already done this experiment"
        )
    return FileResponse("index.html")

@app.get("/version", response_class=PlainTextResponse)
def version():
    return PlainTextResponse("v0.1")