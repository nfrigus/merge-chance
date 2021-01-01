from flask import Flask, request, render_template
import requests as rq
import os
import sys
import logging

app = Flask(__name__)

log = logging.getLogger(__name__)

TOKEN = os.getenv("GH_TOKEN")
STEP_SIZE = 100  # 100 is Max
GH_GQL_URL = "https://api.github.com/graphql"


@app.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@app.route("/target", methods=["GET"])
def target():
    if not TOKEN:
        print("You need to set GH_TOKEN env var")
        sys.exit(1)
    target = request.args.get("repo")
    if not target or "/" not in target:
        return ("No such repository on GitHub", 404)
    owner, repo = target.split("/")
    _, succ, fail = get_stats(owner, repo)
    chance = succ / (fail + succ)
    chance = chance * 100
    chance = round(chance, 2)
    return render_template("chance.html", chance=chance, repo=target)


def calc_chance(stats):
    """Returns total_merged taken into account, outsiders_merged and insiders_merged."""
    total, out_s, out_f = 0, 0, 0
    for edge in stats["data"]["repository"]["pullRequests"]["edges"]:
        node = edge["node"]
        author = node["authorAssociation"]
        state = node["state"]
        if state == "OPEN":
            continue
        total += 1
        if author in {"OWNER", "MEMBER"}:
            continue
        if state == "MERGED":
            out_s += 1
        else:
            out_f += 1
    return total, out_s, out_f


def get_stats(owner, repo):
    result = first_query(owner, repo)
    total, succ, fail = calc_chance(result)
    has_next = result["data"]["repository"]["pullRequests"]["pageInfo"][
        "hasPreviousPage"
    ]
    while total < 100 and has_next:
        cursor = result["data"]["repository"]["pullRequests"]["pageInfo"]["startCursor"]
        result = paginated_query(owner, repo, cursor)
        has_next = result["data"]["repository"]["pullRequests"]["pageInfo"][
            "hasPreviousPage"
        ]
        add_total, add_succ, add_fail = calc_chance(result)
        total += add_total
        succ += add_succ
        fail += add_fail
    return total, succ, fail


def first_query(owner, repo):
    data = {
        "query": """
  query {
    repository(owner:"%s", name:"%s") {
      pullRequests(last: %s) {
        pageInfo {
          hasPreviousPage
          startCursor
        }
        edges {
          cursor
          node {
            state
            authorAssociation
            number
          }
        }
      }
    }
  }
  """
        % (owner, repo, STEP_SIZE)
    }
    return gql_request(data)


def paginated_query(owner, repo, cursor):
    data = {
        "query": """
  query {
    repository(owner:"%s", name:"%s") {
      pullRequests(last: %s, before: "%s") {
        pageInfo {
          hasPreviousPage
          startCursor
        }
        edges {
          cursor
          node {
            state
            authorAssociation
            number
          }
        }
      }
    }
  }
  """
        % (owner, repo, STEP_SIZE, cursor)
    }
    return gql_request(data)


def gql_request(data):
    headers = {"Authorization": f"bearer {TOKEN}"}
    res = rq.post(GH_GQL_URL, headers=headers, json=data)
    return res.json()
