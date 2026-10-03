from typing import List, Optional

from ibm_watsonx_orchestrate.agent_builder.tools import tool, ToolPermission
from ibm_watsonx_orchestrate.run.context import AgentRun

from tools import dropping as drop, enrolment as enr, enrolment_client as service, scheduling as sch
from tools.common import current_student, load, not_found, source


def student_and_blocks(context, availability):
    student, error = current_student(context)
    if error:
        return None, None, error
    try:
        return student, sch.parse_availability(availability), None
    except sch.AvailabilityError as e:
        return None, None, not_found(str(e))


@tool(permission=ToolPermission.READ_ONLY)
def check_enrolment(context: AgentRun, class_ids: List[str], availability: Optional[dict] = None) -> dict:
    """Check whether the logged-in student can enrol in one lecture and one workshop of a course, before enrolling. This changes nothing.

    Use this first whenever the student wants to enrol. Give the two class numbers, one lecture and one workshop of the same course and term (get them from get_timetable). It checks the classes are open and not full, the prerequisites are passed, there is no account hold, the student is not already enrolled or already passed, and the workshop does not clash with their availability or their other classes. If eligible it returns a summary and a check_id. Then show the summary and ask the student to confirm. Never call submit_enrolment in the same reply.

    Args:
        context: The run context supplied by the platform. It is not chosen by the model.
        class_ids: Exactly two class numbers as strings, one lecture and one workshop, for example ["1015", "1102"].
        availability: Optional times the student cannot attend, as a dict like {"busy": [{"days": ["Mon", "Tue", "Wed", "Thu", "Fri"], "start": "09:00", "end": "17:00"}]}.

    Returns:
        found, eligible, reasons (each with a code such as CLASS_FULL, TIMETABLE_CLASH, PREREQUISITE_NOT_MET, ENROLMENT_CLOSED, ACCOUNT_HOLD, INVALID_SELECTION, ALREADY_ENROLLED or ALREADY_PASSED, a message, and alternatives where there are other open classes), a summary of the course, term, lecture and workshop, notes, the check_id, a simulation notice and a source block. If nobody is logged in, found is false.
    """
    student, blocks, error = student_and_blocks(context, availability)
    if error:
        return error
    if service.configured():
        try:
            result = service.check_enrolment(student["student_number"], class_ids, availability)
        except service.ServiceError as e:
            return service.unavailable(e)
        return {"found": True, **result, "served_by": service.SERVED_BY, "source": source(load("timetable.json")[0], "timetable.json")}
    return {"found": True, **enr.check_response(student, class_ids, blocks),
            "source": source(load("timetable.json")[0], "timetable.json")}


@tool(permission=ToolPermission.READ_WRITE)
def submit_enrolment(context: AgentRun, class_ids: List[str], check_id: str, student_confirmed: bool,
                     availability: Optional[dict] = None) -> dict:
    """Enrol the logged-in student in the chosen lecture and workshop. This is a simulation and the only action that changes anything.

    Call this only after check_enrolment said the student is eligible, you showed them the summary, and they clearly said yes in their latest message. Pass the same class numbers, the check_id from check_enrolment, the same availability, and student_confirmed true. If the student said no, or was unclear, do not call this. It refuses if the student has not confirmed, if the check_id does not match, or if the enrolment is no longer possible, and gives a coded error. Always tell the student the result and the simulation notice.

    Args:
        context: The run context supplied by the platform. It is not chosen by the model.
        class_ids: The same two class numbers that were checked.
        check_id: The check_id returned by check_enrolment for these classes.
        student_confirmed: True only if the student explicitly said yes in this conversation.
        availability: The same availability that was used in the check, if any.

    Returns:
        status enrolled with a reference number, the enrolment and a simulation notice, or status refused with an error code (NOT_CONFIRMED, INVALID_CHECK, or a code such as CLASS_FULL, TIMETABLE_CLASH, PREREQUISITE_NOT_MET, ENROLMENT_CLOSED, ACCOUNT_HOLD) and a one-line message. If nobody is logged in, found is false.
    """
    student, blocks, error = student_and_blocks(context, availability)
    if error:
        return error
    if service.configured():
        try:
            return {**service.submit_enrolment(student["student_number"], class_ids, check_id, student_confirmed, availability),
                    "served_by": service.SERVED_BY}
        except service.ServiceError as e:
            return service.unavailable(e)
    return enr.submit_response(student, class_ids, check_id, student_confirmed, blocks)


@tool(permission=ToolPermission.READ_ONLY)
def check_drop(context: AgentRun, course_id: str, term: str) -> dict:
    """Check whether the logged-in student can drop a course they are enrolled in, and what it would cost. This changes nothing.

    Use this first whenever the student wants to drop, withdraw from or leave a class. Give the course code and the term such as 2027-S1 (get them from list_enrolments or get_student_profile). It says if the student is enrolled, whether the census date and the last day to drop without academic penalty have passed, whether the course fee is avoided or still payable, and returns a check_id. Then show the consequences and ask the student to confirm. Never call drop_enrolment in the same reply.

    Args:
        context: The run context supplied by the platform. It is not chosen by the model.
        course_id: The course code, for example COSC2148.
        term: The term of the enrolment, for example 2027-S1.

    Returns:
        found, can_drop, reasons (a code NOT_ENROLLED or DROP_DEADLINE_PASSED with a message), a summary of the course, term, lecture and workshop, consequences (a message to quote, the fee, the census date and drop deadline as text, whether the fee is avoided and whether there is academic penalty), the check_id, a simulation notice and a source block. If nobody is logged in, found is false.
    """
    student, error = current_student(context)
    if error:
        return error
    if service.configured():
        try:
            result = service.check_drop(student["student_number"], course_id, term)
        except ValueError as e:
            return not_found(str(e))
        except service.ServiceError as e:
            return service.unavailable(e)
        return {"found": True, **result, "served_by": service.SERVED_BY, "source": source(load("terms.json")[0], "terms.json")}
    return {"found": True, **drop.check_response(student, course_id, term), "source": source(load("terms.json")[0], "terms.json")}


@tool(permission=ToolPermission.READ_WRITE)
def drop_enrolment(context: AgentRun, course_id: str, term: str, check_id: str, student_confirmed: bool) -> dict:
    """Drop the logged-in student from a course they are enrolled in. This is a simulation.

    Call this only after check_drop said the student can drop, you showed them the consequences, and they clearly said yes in their latest message. Pass the same course and term, the check_id from check_drop, and student_confirmed true. If the student said no, or was unclear, do not call this. It refuses if the student has not confirmed, if the check_id does not match, if they are not enrolled, or if the deadline has passed, and gives a coded error. Always tell the student the result and the simulation notice.

    Args:
        context: The run context supplied by the platform. It is not chosen by the model.
        course_id: The course code that was checked.
        term: The term that was checked.
        check_id: The check_id returned by check_drop for this course and term.
        student_confirmed: True only if the student explicitly said yes in this conversation.

    Returns:
        status dropped with a reference number, the dropped course and its consequences, or status refused with an error code (NOT_CONFIRMED, INVALID_CHECK, NOT_ENROLLED or DROP_DEADLINE_PASSED) and a one-line message, and a simulation notice. If nobody is logged in, found is false.
    """
    student, error = current_student(context)
    if error:
        return error
    if service.configured():
        try:
            return {**service.drop_enrolment(student["student_number"], course_id, term, check_id, student_confirmed),
                    "served_by": service.SERVED_BY}
        except ValueError as e:
            return not_found(str(e))
        except service.ServiceError as e:
            return service.unavailable(e)
    return drop.drop_response(student, course_id, term, check_id, student_confirmed)


@tool(permission=ToolPermission.READ_ONLY)
def list_enrolments(context: AgentRun) -> dict:
    """List the logged-in student's enrolments on record, with the lecture and workshop times of each.

    Use this when the student asks what they are enrolled in or wants their timetable. When the enrolment service is running it includes enrolments made and classes dropped through it, each with its reference. Otherwise it shows the record on file only and enrolments made in this conversation are not included, so report those from the reference numbers given earlier in the conversation.

    Args:
        context: The run context supplied by the platform. It is not chosen by the model.

    Returns:
        found, the enrolments with course, term, status, lecture and workshop, a note about enrolments made in this conversation, and a source block. If nobody is logged in, found is false.
    """
    student, error = current_student(context)
    if error:
        return error
    if service.configured():
        try:
            result = service.list_enrolments(student["student_number"])
        except service.ServiceError as e:
            return service.unavailable(e)
        return {"found": True, "enrolments": result["enrolments"], "served_by": service.SERVED_BY,
                "note": "This list is from the enrolment service. It includes enrolments made and classes dropped in earlier conversations while the service has been running.",
                "simulation_notice": enr.NOTICE, "source": source(student, "students.json")}
    enrolments = enr.describe(student["current_enrolments"])
    return {"found": True, "enrolments": enrolments,
            "note": "This is the record on file. Enrolments made in this conversation are not included, so use the reference numbers you gave earlier.",
            "simulation_notice": enr.NOTICE, "source": source(student, "students.json")}
