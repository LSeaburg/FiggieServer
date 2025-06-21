import os
import pytest
import psycopg
from pathlib import Path
from figgie_server import db

@pytest.fixture(scope="session")
def docker_compose_file(pytestconfig):
    """
    Provide paths to all docker-compose configuration files for pytest-docker.
    """
    project_root = Path(__file__).parent.parent
    return project_root / "tests" / "docker-compose.test.yml"

@pytest.fixture(scope="session", autouse=True)
def test_postgres_database(docker_services, docker_ip):
    """
    Start the PostgreSQL service via docker-compose and configure the test database.
    """
    host = docker_ip
    # Get the mapped port for the 'db' service
    port = docker_services.port_for("db", 5432)
    db_name = "figgie"
    db_user = "figgie"
    db_password = "secret_password"

    # Define a check function that attempts to connect to the database
    def is_postgres_responsive(ip, port):
        try:
            conn = psycopg.connect(
                host=ip,
                port=port,
                dbname=db_name,
                user=db_user,
                password=db_password,
            )
            conn.close()
            return True
        except psycopg.OperationalError:
            return False

    # Wait until the service is responsive
    docker_services.wait_until_responsive(
        timeout=30.0,
        pause=0.5,
        check=lambda: is_postgres_responsive(host, port),
    )

    # Set environment variables for database connection
    os.environ["DB_HOST"] = host
    os.environ["DB_PORT"] = str(port)
    os.environ["DB_NAME"] = "figgie"
    os.environ["DB_USER"] = "figgie"
    os.environ["DB_PASSWORD"] = "secret_password"

    # Reset any existing singleton connection
    db._conn = None

    # Initialize the database schema
    db.init_db()

    yield

    # Tear-down: close the connection
    conn = db.get_connection()
    conn.close()
