from django.apps import AppConfig


class PatientsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'patients'
    default = True

    def ready(self):
        # Wire the post_save signal handlers (SignupRequest email notifier).
        # Importing here is the standard Django pattern — the import has
        # the side-effect of registering @receiver decorators.
        from . import signals  # noqa: F401
