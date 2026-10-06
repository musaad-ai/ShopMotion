"""Flask CLI commands: ``flask init-db``, ``flask create-admin``, ``flask seed-demo``."""
import click

from .extensions import db
from .models import User


def register_cli(app):
    @app.cli.command("init-db")
    def init_db():
        """Create tables and the default store layout + camera."""
        from .seed import ensure_defaults

        db.create_all()
        ensure_defaults()
        click.echo("Database ready.")

    @app.cli.command("create-admin")
    @click.option("--username", prompt=True)
    @click.option("--email", prompt=True)
    @click.password_option()
    def create_admin(username, email, password):
        """Create an administrator account."""
        if User.query.filter_by(username=username).first():
            raise click.ClickException("Username already exists")
        user = User(username=username, email=email.lower(), role="admin")
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        click.echo(f"Admin '{username}' created.")

    @app.cli.command("seed-demo")
    @click.option("--days", default=30, show_default=True, help="Days of history to generate")
    @click.option("--reset/--no-reset", default=True, show_default=True, help="Wipe analytics data first")
    def seed_demo(days, reset):
        """Fill the database with realistic synthetic analytics + demo users."""
        from .seed import seed_demo_data

        stats = seed_demo_data(days=days, reset=reset)
        click.echo(", ".join(f"{k}: {v}" for k, v in stats.items()))
        click.echo("Demo accounts -> admin / admin123   viewer / viewer123")
