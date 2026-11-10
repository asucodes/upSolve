"""Local catalog browsing and personalized topic practice, without scraping tutorials."""

from . import coach

# Curated CF-tag mappings inspired by the linked topic indexes, not an official
# USACO curriculum or a claim that a CF difficulty equals a USACO division.
CP = "https://cp-algorithms.com/"
TOPICS = [
    {
        "id": "fundamentals",
        "name": "Implementation and sorting",
        "tags": ["implementation", "sortings", "brute force"],
        "resource": "https://usaco.guide/general/resources-cp",
    },
    {
        "id": "searching",
        "name": "Binary search and two pointers",
        "tags": ["binary search", "two pointers", "ternary search"],
        "resource": CP + "num_methods/binary_search.html",
    },
    {
        "id": "greedy",
        "name": "Greedy and constructive algorithms",
        "tags": ["greedy", "constructive algorithms"],
        "resource": CP,
    },
    {
        "id": "dp",
        "name": "Dynamic programming",
        "tags": ["dp"],
        "resource": CP + "dynamic_programming/intro-to-dp.html",
    },
    {
        "id": "graphs",
        "name": "Graph algorithms",
        "tags": [
            "graphs",
            "dfs and similar",
            "shortest paths",
            "flows",
            "graph matchings",
            "2-sat",
        ],
        "resource": CP + "graph/breadth-first-search.html",
    },
    {"id": "trees", "name": "Trees", "tags": ["trees", "dsu"], "resource": CP},
    {
        "id": "data-structures",
        "name": "Data structures",
        "tags": ["data structures", "dsu"],
        "resource": CP + "data_structures/segment_tree.html",
    },
    {
        "id": "number-theory",
        "name": "Mathematics and number theory",
        "tags": ["math", "number theory"],
        "resource": CP + "algebra/binary-exp.html",
    },
    {
        "id": "combinatorics",
        "name": "Combinatorics and probability",
        "tags": ["combinatorics", "probabilities"],
        "resource": CP + "combinatorics/binomial-coefficients.html",
    },
    {
        "id": "strings",
        "name": "String algorithms",
        "tags": ["strings", "string suffix structures", "hashing"],
        "resource": CP + "string/string-hashing.html",
    },
    {
        "id": "geometry",
        "name": "Geometry",
        "tags": ["geometry"],
        "resource": CP + "geometry/basic-geometry.html",
    },
    {
        "id": "bitmasks",
        "name": "Bitmasks and games",
        "tags": ["bitmasks", "games"],
        "resource": CP,
    },
]


def category(id):
    return next((t for t in TOPICS if t["id"] == id), None)


def serialize(p, solved, attempted, sample=False):
    k = coach.key(p)
    return {
        **p,
        "key": k,
        "status": "solved"
        if k in solved
        else "attempted"
        if k in attempted
        else "unattempted",
        "url": None
        if sample
        else f"https://codeforces.com/problemset/problem/{p['contestId']}/{p['index']}",
    }


def browse(
    catalog,
    analysis,
    *,
    search="",
    tag="",
    category_id="",
    minimum=800,
    maximum=4000,
    state="all",
    sort="newest",
    page=1,
    page_size=25,
    include_unrated=True,
    sample=False,
):
    solved = set(analysis["solved"])
    attempted = set(analysis["attempted"])
    group = category(category_id) if category_id else None
    rows = []
    for p in catalog:
        if not p.get("contestId") or p.get("type", "PROGRAMMING") != "PROGRAMMING":
            continue
        tags = p.get("tags", [])
        if (
            search
            and search.casefold()
            not in (p["name"] + " " + str(p["contestId"]) + p["index"]).casefold()
        ):
            continue
        if tag and tag not in tags:
            continue
        if group and not set(group["tags"]).intersection(tags):
            continue
        if p.get("rating") is None:
            if not include_unrated:
                continue
        elif not minimum <= p["rating"] <= maximum:
            continue
        item = serialize(p, solved, attempted, sample)
        if state == "solved" and item["status"] != "solved":
            continue
        if state == "attempted" and item["status"] != "attempted":
            continue
        if state == "unattempted" and item["status"] != "unattempted":
            continue
        rows.append(item)
    if sort == "difficulty":
        rows.sort(
            key=lambda p: (
                p.get("rating") if p.get("rating") is not None else 99999,
                p["contestId"],
                p["index"],
            )
        )
    else:
        rows.sort(key=lambda p: (p["contestId"], p["index"]), reverse=True)
    start = (page - 1) * page_size
    return {
        "total": len(rows),
        "page": page,
        "page_size": page_size,
        "pages": max(1, (len(rows) + page_size - 1) // page_size),
        "items": rows[start : start + page_size],
    }


def gym(catalog, analysis, rating, sample=False):
    solved = set(analysis["solved"])
    attempted = set(analysis["attempted"])
    result = []
    for topic in TOPICS:
        rows = [
            p
            for p in catalog
            if set(p.get("tags", [])) & set(topic["tags"])
            and p.get("type", "PROGRAMMING") == "PROGRAMMING"
        ]
        recommendations = coach.recommend(rows, analysis, rating=rating)
        if sample:
            for p in recommendations:
                p["url"] = None
        keys = {coach.key(p) for p in rows}
        result.append(
            {
                **topic,
                "catalog_problems": len(keys),
                "solved": len(keys & solved),
                "attempted_unsolved": len((keys & attempted) - solved),
                "recommendations": recommendations,
            }
        )
    return {
        "rating_reference": rating if rating is not None else 1000,
        "provisional_rating": rating is None,
        "topics": result,
        "taxonomy_note": "Curated Codeforces tag groups inspired by CP-Algorithms and USACO Guide. Not an official curriculum or USACO division mapping.",
    }
