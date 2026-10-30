from rest_framework.exceptions import APIException


class VersionConflict(APIException):
    status_code = 409
    default_code = "stale_dispute_version"
    default_detail = (
        "The objection has changed. Review its current version and prepare a new draft."
    )


class PreviewConflict(APIException):
    status_code = 409
    default_code = "stale_objection_preview"
    default_detail = "The draft's context has changed. Refresh and review before signing."


class ResponseWindowClosed(APIException):
    status_code = 409
    default_code = "response_window_closed"
    default_detail = (
        "The simulation is outside this candidate response window. "
        "Supplementary evidence remains available."
    )
