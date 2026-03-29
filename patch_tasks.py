import os
import re

task_types = """class TaskType:
    AT_WORK = "at_work"
    IDLE = "idle"
    AT_HOME = "at_home"
    WANDERING = "wandering"
    SITTING = "sitting"
    FORGING = "forging"
    SLEEPING = "sleeping"
    GOING_HOME = "going_home"
    GOING_HOME_TO_SLEEP = "going_home_to_sleep"
    GOING_TO_BED = "going_to_bed"
    GOING_TO_WORK = "going_to_work"
    LOOKING_FOR_WORK = "looking_for_work"
    WORKING_AT_STATION = "working_at_station"
    SOCIALIZING = "socializing"
    CONVERSING = "conversing"
    TRADING = "trading"
    EATING = "eating"
"""

with open("simulation/systems/task_types.py", "w") as f:
    f.write(task_types)
