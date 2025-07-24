from django.urls import path

from . import (
    AppointmentView,
    AppointmentDetailView,
    AppointmentTypeView,
    DoctorView,
    DoctorsOfficeLocationView,
    RoomView,
    BlockerView,
    BulkBlockerView,
    RescheduleAppointmentView,
    LocationBlockerView,
)
from .file_handle_view import FileHandleView
from .appointment_search_view import AppointmentSearchView
from .patient_search_view import PatientSearchView
from .blocker_search_view import BlockerSearchView
from .bookable_slot_view import BookableSlotView
from .meeting_lookup_view import MeetingLookupView

urlpatterns = [
    path("appointments/", AppointmentView.as_view(http_method_names=['get', 'post', 'put', 'delete']), name="appointment-list"),
    path("appointments/detail/<int:appointment_id>/", AppointmentDetailView.as_view(http_method_names=['get']), name="appointment-detail"),
    path("appointments/by-meeting-id/", MeetingLookupView.as_view(http_method_names=['post']), name="appointment-meeting-lookup"),
    path("appointments/status/", AppointmentView.as_view(http_method_names=['post', 'put']), name="appointment-status-update"),
    path("appointments/piz/", AppointmentView.as_view(http_method_names=['post', 'put']), name="appointment-piz-update"),
    path("appointments/update/", AppointmentView.as_view(http_method_names=['post', 'put']), name="appointment-update"),
    path("appointments/move/", AppointmentView.as_view(http_method_names=['post', 'put']), name="appointment-move"),
    path("appointments/reschedule/", RescheduleAppointmentView.as_view(http_method_names=['get', 'post']), name="appointment-reschedule"),
    path("appointments/file-handle/", FileHandleView.as_view(http_method_names=['get', 'post']), name="appointment-file-handle"),
    
    path("appointment_search/", AppointmentSearchView.as_view(http_method_names=['get']), name="appointment-search"),
    path("patient_search/", PatientSearchView.as_view(http_method_names=['get', 'post']), name="patient-search"),
    
    path("blockers/", BlockerView.as_view(http_method_names=['get', 'post', 'delete']), name="blocker-list"),
    path("bulk-blockers/", BulkBlockerView.as_view(http_method_names=['get', 'post', 'put']), name="bulk-blocker"),
    path("location-blockers/", LocationBlockerView.as_view(http_method_names=['get']), name="location-blocker-list"),
    path("blocker_search/", BlockerSearchView.as_view(http_method_names=['get']), name="blocker-search"),
   
    path("doctors/", DoctorView.as_view(http_method_names=['get']), name="doctor-list"),
    path("rooms/", RoomView.as_view(http_method_names=['get']), name="room-list"),
    path("bookable-slots/", BookableSlotView.as_view(http_method_names=['get']), name="bookable-slots"),
    path(
        "appointment-types/",
        AppointmentTypeView.as_view(http_method_names=['get']),
        name="appointment-type-list",
    ),
    path(
        "doctors-office-locations/",
        DoctorsOfficeLocationView.as_view(http_method_names=['get']),
        name="doctors-office-location-list",
    ),
]
