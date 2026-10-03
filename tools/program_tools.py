from typing import Optional

from ibm_watsonx_orchestrate.agent_builder.tools import tool, ToolPermission
from ibm_watsonx_orchestrate.run.context import AgentRun

from tools import programs as prog
from tools.common import current_student, load, not_found, source


@tool(permission=ToolPermission.READ_ONLY)
def lookup_program(context: AgentRun, program_code: Optional[str] = None) -> dict:
    """Get the structure of a program: its stages or years, the compulsory courses, the credit points of options and choices each stage needs, the option list, majors and minors, total credit points, duration, study loads, intakes, entry score, fees and campus.

    Use this for questions about what a program contains, how many credit points it is, how long it takes full-time or part-time, what is compulsory, which option courses can be chosen, which majors and minors exist, the entry score or the intake. Leave program_code empty for the logged-in student's own program. Pass a code such as BP094P23 to look at another program, for example to compare programs. programs_with_data lists every program there is data for. For what a student still needs for one major or minor, use get_major_minor_progress.

    Args:
        context: The run context supplied by the platform. It is not chosen by the model.
        program_code: Optional program code such as BH013P26, BP094P23 or BP162P23. Leave empty for the student's program.

    Returns:
        found, the program (stages, compulsory courses, choices, option list, majors and minors by name, total credit points, duration, study loads and the minimum number of semesters at each load), programs_with_data, published_fields and a source block. If the program code is unknown, found is false with a reason.
    """
    student, _ = current_student(context)
    if program_code:
        program = prog.get_program(program_code)
        if program is None:
            return prog.unknown_program(program_code)
    elif student:
        program = prog.program_for(student)
    else:
        return not_found("Give a program code, for example BH013P26. Programs with data: " +
                         ", ".join(p["program_code"] for p in prog.all_programs()))
    courses = {c["course_id"]: c for c in load("courses.json")}

    def brief(course_id: str) -> dict:
        return {"course_id": course_id, "title": courses[course_id]["title"],
                "credit_points": courses[course_id]["credit_points"]}

    per_semester = program["study_load"]
    total = program["total_credit_points"]
    stages = []
    for s in program["stages"]:
        stage = {
            "stage": s["stage"],
            "credit_points": sum(i["credit_points"] if i["type"] != "course" else courses[i["course_id"]]["credit_points"]
                                 for i in s["items"]),
            "compulsory_courses": [brief(c) for c in prog.course_ids(s)],
            "compulsory_credit_points": prog.compulsory_credit_points(s, {c: v["credit_points"] for c, v in courses.items()}),
            "option_credit_points": prog.option_credit_points(s),
            "note": s.get("note"),
        }
        choices = [{"credit_points": i["credit_points"], "one_of": [brief(c) for c in i["course_ids"]]}
                   for i in s["items"] if i["type"] == "choice"]
        if choices:
            stage["choices"] = choices
        stages.append(stage)
    record = {
        "program_code": program["program_code"],
        "title": program["title"],
        "campus": program["campus"],
        "intakes": program["intakes"],
        "duration": program["duration"],
        "total_credit_points": total,
        "study_load": per_semester,
        "minimum_semesters": {
            **{load_name: -(-total // per_semester[f"{load_name}_cp_per_semester"])
               for load_name in ("full_time", "part_time") if f"{load_name}_cp_per_semester" in per_semester},
            "how": "total credit points divided by the credit points per semester at that load",
        },
        "stages": stages,
        "option_list": {"title": program["option_list"]["title"],
                        "courses": [brief(c) for c in program["option_list"]["course_ids"]]},
    }
    for extra in ("level", "entry_score", "places"):
        if program.get(extra):
            record[extra] = program[extra]
    if program.get("majors") or program.get("minors"):
        record["majors"] = [{"name": m["name"], "credit_points": m["credit_points"]} for m in program.get("majors", [])]
        record["minors"] = [{"name": m["name"], "credit_points": m["credit_points"], "cross_disciplinary": m.get("cross_disciplinary", False)}
                            for m in program.get("minors", [])]
        record["majors_and_minors_note"] = program.get("majors_and_minors_note")
    return {
        "found": True,
        "program": record,
        "programs_with_data": [{"program_code": p["program_code"], "title": p["title"],
                                "total_credit_points": p["total_credit_points"], "duration": p["duration"]}
                               for p in prog.all_programs()],
        "published_fields": list(program["field_provenance"]),
        "source": source(program, "programs.json"),
    }
