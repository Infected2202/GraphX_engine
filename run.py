"""Entry point for running the GraphX web application."""

from graphx_web import create_app

app = create_app()

if __name__ == "__main__":
    app.run()
