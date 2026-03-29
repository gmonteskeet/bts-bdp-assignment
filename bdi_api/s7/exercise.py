from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel
from neo4j import GraphDatabase

from bdi_api.settings import Settings

settings = Settings()

s7 = APIRouter(
    responses={
        status.HTTP_404_NOT_FOUND: {"description": "Not found"},
        status.HTTP_422_UNPROCESSABLE_ENTITY: {"description": "Something is wrong with the request"},
    },
    prefix="/api/s7",
    tags=["s7"],
)


class PersonCreate(BaseModel):
    name: str
    city: str
    age: int


class RelationshipCreate(BaseModel):
    from_person: str
    to_person: str
    relationship_type: str = "FRIENDS_WITH"


def _get_driver():
    """Helper to get the Neo4j driver."""
    return GraphDatabase.driver(
        settings.neo4j_url,
        auth=(settings.neo4j_user, settings.neo4j_password),
    )

def _normalize_name(name: str) -> str:
    """Normalize name: strip whitespace, capitalize first letter, lowercase rest."""
    return name.strip().capitalize()

@s7.post("/graph/person")
def create_person(person: PersonCreate) -> dict:
    """Create a person node in Neo4J.

    Use the BDI_NEO4J_URL environment variable to configure the connection.
    Start Neo4J with: make neo4j
    """
    normalized_name = _normalize_name(person.name)
    # TODO: Connect to Neo4J using neo4j.GraphDatabase.driver(settings.neo4j_url, auth=(settings.neo4j_user, settings.neo4j_password))
    driver = _get_driver()
    # TODO: Create a Person node with the given properties
    with driver.session() as session:
        session.run(
            "MERGE (p:Person {name: $name}) SET p.city = $city, p.age = $age",
            name=normalized_name,
            city=person.city,
            age=person.age,
        )
    driver.close()
    # TODO: Return {"status": "ok", "name": person.name}
    return {"status": "ok", "name": normalized_name}


@s7.get("/graph/persons")
def list_persons() -> list[dict]:
    """List all person nodes."""
    driver = _get_driver()
    with driver.session() as session:
        result = session.run("MATCH (p:Person) RETURN p")
        persons = [
            {
                "name": record["p"]["name"],
                "city": record["p"]["city"],
                "age": record["p"]["age"]
            }
            for record in result
        ]
    driver.close()
    return persons


@s7.get("/graph/person/{name}/friends")
def get_friends(name: str) -> list[dict]:
    """Get friends of a person.

    Returns all persons connected by a FRIENDS_WITH relationship (any direction).
    If person not found, return 404.
    """
    name = _normalize_name(name)
    driver = _get_driver()
    with driver.session() as session:
        # Check if person exists
        check = session.run(
            "MATCH (p:Person {name: $name}) RETURN p",
            name=name,
        )
        if not check.single():
            driver.close()
            raise HTTPException(status_code=404, detail=f"Person '{name}' not found")

        result = session.run(
            "MATCH (p:Person {name: $name})-[:FRIENDS_WITH]-(friend:Person) RETURN friend",
            name=name,
        )
        friends = [
            {"name": record["friend"]["name"], "city": record["friend"]["city"], "age": record["friend"]["age"]}
            for record in result
        ]
    driver.close()
    return friends


@s7.post("/graph/relationship")
def create_relationship(rel: RelationshipCreate) -> dict:
    """Create a relationship between two persons.

    Both persons must exist. Returns 404 if either is not found.
    """
    from_name = _normalize_name(rel.from_person)
    to_name = _normalize_name(rel.to_person)
    driver = _get_driver()
    with driver.session() as session:
        # Verify both persons exist
        result_from = session.run(
            "MATCH (p:Person {name: $name}) RETURN p",
            name=from_name,
        )
        if not result_from.single():
            driver.close()
            raise HTTPException(status_code=404, detail=f"Person '{from_name}' not found")

        result_to = session.run(
            "MATCH (p:Person {name: $name}) RETURN p",
            name=to_name,
        )
        if not result_to.single():
            driver.close()
            raise HTTPException(status_code=404, detail=f"Person '{to_name}' not found")

        session.run(
            "MATCH (a:Person {name: $from_name}), (b:Person {name: $to_name}) "
            "MERGE (a)-[:FRIENDS_WITH]->(b)",
            from_name=from_name,
            to_name=to_name,
        )
    driver.close()
    return {"status": "ok", "from": from_name, "to": to_name}


@s7.get("/graph/person/{name}/recommendations")
def get_recommendations(name: str) -> list[dict]:
    """Get friend recommendations for a person.

    Recommend friends-of-friends who are NOT already direct friends.
    Return them sorted by number of mutual friends (descending).
    If person not found, return 404.

    Each result should include: name, city, mutual_friends (count).
    """
    name = _normalize_name(name)
    # TODO: Connect to Neo4J
    driver = _get_driver()
    with driver.session() as session:
        # Check if person exists
        check = session.run(
            "MATCH (p:Person {name: $name}) RETURN p",
            name=name,
        )
        # TODO: First check if person exists, return 404 if not
        if not check.single():
            driver.close()
            raise HTTPException(status_code=404, detail=f"Person '{name}' not found")

        # TODO: Find friends-of-friends not already friends
        # TODO: Count mutual friends and sort descending
        result = session.run(
            "MATCH (p:Person {name: $name})-[:FRIENDS_WITH]-(friend)-[:FRIENDS_WITH]-(fof:Person) "
            "WHERE fof <> p AND NOT (p)-[:FRIENDS_WITH]-(fof) "
            "RETURN fof.name AS name, fof.city AS city, count(DISTINCT friend) AS mutual_friends "
            "ORDER BY mutual_friends DESC",
            name=name,
        )
        recommendations = [
            {"name": record["name"], "city": record["city"], "mutual_friends": record["mutual_friends"]}
            for record in result
        ]
    driver.close()
    return recommendations
