#***************************************************************************
#*                                                                         *
#*   Copyright (c) 2011, 2016 Jose Luis Cercos Pita <jlcercos@gmail.com>   *
#*                                                                         *
#***************************************************************************

def load():
    """Load the ship creation tool"""
    # Wichtig: Hier wird TaskPanel.createTask() erwartet
    from . import TaskPanel
    return TaskPanel.createTask()
