import argparse
import csv
import random
from datetime import datetime
from pathlib import Path

from psychopy import prefs
prefs.hardware['audioLib'] = ['ptb']
prefs.hardware['audioDevice'] = 'Headphones(High Definition Audio Device)'

from psychopy import visual, core, event, sound
from explorepy import Explore

# ---------------------------------------------------------------------------
# EEG event markers
# ---------------------------------------------------------------------------
SESSION_START = 1
RELAX_ONSET = 5
FIXATION_ONSET = 10
CUE_LEFT_ONSET = 11
CUE_RIGHT_ONSET = 12
TASK_LEFT_ONSET = 21
TASK_RIGHT_ONSET = 22
TRIAL_REST_ONSET = 30
INTER_RUN_REST_ONSET = 40
SESSION_END = 99
EXPERIMENT_ABORTED = 98

# Run-specific markers:
# Run 1 start = 101, ..., Run 5 start = 105
# Run 1 end   = 201, ..., Run 5 end   = 205
RUN_START_BASE = 100
RUN_END_BASE = 200


class ExperimentAbort(Exception):
    """Raised when the participant or experimenter presses Escape."""


def parse_arguments():
    parser = argparse.ArgumentParser(
        description=(
            "Collect 2-class left/right hand motor-imagery EEG data "
            "using PsychoPy and an Explore EEG device."
        )
    )
    parser.add_argument(
        "-n",
        "--name",
        dest="device_name",
        type=str,
        required=True,
        help="Explore EEG device name.",
    )
    parser.add_argument(
        "-f",
        "--filename",
        dest="filename",
        type=str,
        required=True,
        help="Base name for the session. Also used as the output folder name.",
    )
    parser.add_argument(
        "-o",
        "--outdir",
        dest="outdir",
        type=str,
        default="data",
        help="Root directory that holds all session folders. Default: data",
    )
    parser.add_argument(
        "--timestamp",
        action="store_true",
        help=(
            "Append a date/time suffix to the session folder so that repeated "
            "runs never collide with existing files."
        ),
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=None,
        help="Optional random seed for reproducible cue order.",
    )
    parser.add_argument(
        "--screen",
        type=int,
        default=0,
        help="Monitor number used for stimulus presentation. Default: 0.",
    )
    parser.add_argument(
        "--windowed",
        action="store_true",
        help="Run in a window instead of full-screen mode.",
    )
    return parser.parse_args()


def check_escape():
    """Immediately abort the experiment when Escape is pressed."""
    if "escape" in event.getKeys(keyList=["escape"]):
        raise ExperimentAbort


def make_balanced_conditions(rng, trials_per_run):
    """
    Create a balanced randomized cue list.

    For 60 trials, this returns exactly:
    - 30 left-hand trials
    - 30 right-hand trials
    """
    if trials_per_run % 2 != 0:
        raise ValueError("trials_per_run must be an even number.")

    half = trials_per_run // 2
    conditions = ["left"] * half + ["right"] * half
    rng.shuffle(conditions)
    return conditions


def build_output_paths(args):
    """
    Create the session folder and return the paths of every output file.

    Layout, for `-o data -f sub01`:

        data/
          sub01/
            sub01.csv             <- EEG recording written by explorepy
            sub01_trial_log.csv   <- behavioral log written by this script

    With --timestamp the folder becomes `sub01_20260804_143012` so that a
    repeated run never collides with existing files.
    """
    session_name = Path(args.filename).name
    if args.timestamp:
        session_name = f"{session_name}_{datetime.now():%Y%m%d_%H%M%S}"

    output_dir = Path(args.outdir).expanduser().resolve() / session_name
    output_dir.mkdir(parents=True, exist_ok=True)

    # explorepy appends its own suffix and extension to this base path.
    eeg_base = output_dir / session_name
    log_path = output_dir / f"{session_name}_trial_log.csv"

    return output_dir, eeg_base, log_path


def main():
    args = parse_arguments()

    # -----------------------------------------------------------------------
    # Experiment design
    # -----------------------------------------------------------------------
    n_sessions = 1
    n_runs = 5
    trials_per_run = 60

    fixation_duration = 2.0
    cue_duration = 0.7
    task_duration = 3.0
    trial_rest_duration = 2.0
    inter_run_rest_duration = 25.0
    initial_relax_duration = 5.0
    relax_end_beep_duration = 1.0

    rng = random.Random(args.seed)

    # -----------------------------------------------------------------------
    # Output paths
    # -----------------------------------------------------------------------
    # The folder is created before the EEG recording starts so that both the
    # EEG file and the behavioral log end up inside it.
    output_dir, eeg_base, log_path = build_output_paths(args)
    print(f"Output folder: {output_dir}")

    if log_path.exists():
        raise FileExistsError(
            f"{log_path} already exists. Use a different -f name, "
            f"or add --timestamp."
        )

    # -----------------------------------------------------------------------
    # PsychoPy window and stimuli
    # -----------------------------------------------------------------------
    win = visual.Window(
        size=(3440, 1440),
        fullscr=not args.windowed,
        screen=args.screen,
        units="height",
        color=(0.1, 0.1, 0.1),
        colorSpace="rgb",
        allowGUI=args.windowed,
    )

    # Stimulus color: black
    stim_color = (-1, -1, -1)

    # Fixation cross - horizontal bar
    fixation_cross_horizontal = visual.Rect(
        win=win,
        width=0.07,
        height=0.010,
        pos=(0, 0),
        fillColor=stim_color,
        lineColor=stim_color,
        units="height",
    )

    # Fixation cross - vertical bar
    fixation_cross_vertical = visual.Rect(
        win=win,
        width=0.010,
        height=0.07,
        pos=(0, 0),
        fillColor=stim_color,
        lineColor=stim_color,
        units="height",
    )

    fixation_cross = [
        fixation_cross_horizontal,
        fixation_cross_vertical
    ]

    # Central circle used in Cue, and Task.
    fixation_circle = visual.Circle(
        win=win,
        radius=0.035,
        edges=128,
        pos=(0, 0),
        fillColor=stim_color,
        lineColor=stim_color,
        lineWidth=1,
        units="height",
    )

    # Left arrow attached to the central circle.
    left_arrow = visual.ShapeStim(
        win=win,
        vertices=[
            (-0.005,  0.014),
            (-0.060,  0.014),
            (-0.060,  0.032),
            (-0.105,  0.000),
            (-0.060, -0.032),
            (-0.060, -0.014),
            (-0.005, -0.014),
        ],
        closeShape=True,
        fillColor=stim_color,
        lineColor=stim_color,
        lineWidth=1,
        units="height",
    )

    # Right arrow attached to the central circle.
    right_arrow = visual.ShapeStim(
        win=win,
        vertices=[
            (0.005,  0.014),
            (0.060,  0.014),
            (0.060,  0.032),
            (0.105,  0.000),
            (0.060, -0.032),
            (0.060, -0.014),
            (0.005, -0.014),
        ],
        closeShape=True,
        fillColor=stim_color,
        lineColor=stim_color,
        lineWidth=1,
        units="height",
    )

    # Draw the arrow first and the circle second.
    # This makes the arrow look attached behind the circle.
    left_cue = [left_arrow, fixation_circle]
    right_cue = [right_arrow, fixation_circle]

    instruction_text = visual.TextStim(
        win=win,
        text=(
            "Motor Imagery EEG Experiment\n\n"
            "Left arrow: imagine repeatedly moving your LEFT hand.\n"
            "Right arrow: imagine repeatedly moving your RIGHT hand.\n\n"
            "Keep your body still and look at the center of the screen.\n"
            "Perform the imagery while the circle is displayed after the arrow.\n\n"
            "Press SPACE to begin."
        ),
        height=0.035,
        color=(-1, -1, -1),
        wrapWidth=1.4,
        units="height",
    )

    relax_text = visual.TextStim(
        win=win,
        text="RELAX",
        height=0.08,
        color=(-1, -1, -1),
        units="height",
    )

    inter_run_text = visual.TextStim(
        win=win,
        text="Rest",
        height=0.08,
        color=(-1, -1, -1),
        units="height",
    )

    finished_text = visual.TextStim(
        win=win,
        text="Session complete.\nThank you.",
        height=0.06,
        color=(-1, -1, -1),
        units="height",
    )

    # Short beep played when the initial RELAX stage ends.
    relax_end_beep = sound.Sound(
        value=1000,
        secs=relax_end_beep_duration,
        stereo=True,
    )

    global_clock = core.Clock()

    # -----------------------------------------------------------------------
    # Explore EEG setup
    # -----------------------------------------------------------------------
    explore = Explore()
    connected = False
    recording = False

    # Each row stores one complete trial.
    log_fields = [
        "session",
        "run",
        "trial",
        "condition",
        "fixation_marker",
        "cue_marker",
        "task_marker",
        "rest_marker",
        "fixation_onset_s",
        "cue_onset_s",
        "task_onset_s",
        "rest_onset_s",
        "trial_end_s",
    ]

    def marker_and_timestamp(marker, holder):
        """
        Called by PsychoPy immediately after the next screen flip.

        This makes the visual onset timestamp and Explore marker as closely
        synchronized with the display refresh as possible.
        """
        holder["time"] = global_clock.getTime()
        explore.set_marker(marker)

    def show_stage(stimulus, duration, marker):
        """
        Display one stimulus, or a blank screen when stimulus is None,
        for the requested duration.

        Escape is checked throughout the stage.
        """
        event.clearEvents(eventType="keyboard")

        if stimulus is not None:
            if isinstance(stimulus, (list, tuple)):
                for stim in stimulus:
                    stim.draw()
            else:
                stimulus.draw()

        onset = {}
        stage_clock = core.Clock()

        win.callOnFlip(stage_clock.reset)
        win.callOnFlip(marker_and_timestamp, marker, onset)
        win.flip()

        while stage_clock.getTime() < duration:
            check_escape()
            core.wait(0.005)

        return onset["time"]

    def wait_with_escape(duration):
        """Wait for the requested duration while still honouring Escape."""
        wait_clock = core.Clock()
        while wait_clock.getTime() < duration:
            check_escape()
            core.wait(0.01)

    def show_message_and_wait_for_space(stimulus):
        event.clearEvents(eventType="keyboard")
        stimulus.draw()
        win.flip()

        while True:
            keys = event.getKeys(keyList=["space", "escape"])
            if "escape" in keys:
                raise ExperimentAbort
            if "space" in keys:
                break
            core.wait(0.01)

    try:
        # Connect to the Explore device and begin EEG recording.
        explore.connect(device_name=args.device_name)
        connected = True

        # Writing to eeg_base keeps the EEG file inside the session folder.
        explore.record_data(
            file_name=str(eeg_base),
            file_type="csv",
            do_overwrite=False,
        )
        recording = True

        with log_path.open("x", newline="", encoding="utf-8-sig") as log_file:
            writer = csv.DictWriter(log_file, fieldnames=log_fields)
            writer.writeheader()

            # Initial task instructions.
            show_message_and_wait_for_space(instruction_text)

            global_clock.reset()
            explore.set_marker(SESSION_START)

            # Initial relaxation period before Run 1.
            show_stage(
                stimulus=relax_text,
                duration=initial_relax_duration,
                marker=RELAX_ONSET,
            )

            # Signal the end of RELAX, then begin Run 1.
            # The beep length is timed explicitly instead of polling
            # relax_end_beep.isFinished, whose type differs across
            # PsychoPy versions.
            relax_end_beep.play()
            wait_with_escape(relax_end_beep_duration)

            # Keep the RELAX screen for 1 additional second
            # after the beep has completely finished.
            wait_with_escape(1.0)

            # The requested design contains one session.
            for session_number in range(1, n_sessions + 1):
                for run_number in range(1, n_runs + 1):
                    run_start_marker = RUN_START_BASE + run_number
                    explore.set_marker(run_start_marker)

                    # Exactly 30 left and 30 right trials per run.
                    conditions = make_balanced_conditions(
                        rng=rng,
                        trials_per_run=trials_per_run,
                    )

                    for trial_number, condition in enumerate(conditions, start=1):
                        cue_stimulus = (
                            left_cue if condition == "left" else right_cue
                        )
                        cue_marker = (
                            CUE_LEFT_ONSET
                            if condition == "left"
                            else CUE_RIGHT_ONSET
                        )
                        task_marker = (
                            TASK_LEFT_ONSET
                            if condition == "left"
                            else TASK_RIGHT_ONSET
                        )

                        # 1. Fixation: cross cue.
                        fixation_onset = show_stage(
                            stimulus=fixation_cross,
                            duration=fixation_duration,
                            marker=FIXATION_ONSET,
                        )

                        # 2. Cue: left or right arrow.
                        cue_onset = show_stage(
                            stimulus=cue_stimulus,
                            duration=cue_duration,
                            marker=cue_marker,
                        )

                        # 3. Task: circular cue.
                        # The participant performs the instructed motor imagery.
                        task_onset = show_stage(
                            stimulus=fixation_circle,
                            duration=task_duration,
                            marker=task_marker,
                        )

                        # 4. Rest: blank screen.
                        rest_onset = show_stage(
                            stimulus=None,
                            duration=trial_rest_duration,
                            marker=TRIAL_REST_ONSET,
                        )

                        writer.writerow(
                            {
                                "session": session_number,
                                "run": run_number,
                                "trial": trial_number,
                                "condition": condition,
                                "fixation_marker": FIXATION_ONSET,
                                "cue_marker": cue_marker,
                                "task_marker": task_marker,
                                "rest_marker": TRIAL_REST_ONSET,
                                "fixation_onset_s": f"{fixation_onset:.6f}",
                                "cue_onset_s": f"{cue_onset:.6f}",
                                "task_onset_s": f"{task_onset:.6f}",
                                "rest_onset_s": f"{rest_onset:.6f}",
                                "trial_end_s": f"{global_clock.getTime():.6f}",
                            }
                        )
                        log_file.flush()

                    run_end_marker = RUN_END_BASE + run_number
                    explore.set_marker(run_end_marker)

                    # A longer rest is inserted only between runs.
                    if run_number < n_runs:
                        show_stage(
                            stimulus=inter_run_text,
                            duration=inter_run_rest_duration,
                            marker=INTER_RUN_REST_ONSET,
                        )

            explore.set_marker(SESSION_END)

            # End message.
            finished_text.draw()
            win.flip()
            core.wait(3.0)

    except ExperimentAbort:
        if connected:
            try:
                explore.set_marker(EXPERIMENT_ABORTED)
            except Exception:
                pass
        print("Experiment aborted with the Escape key.")

    finally:
        if recording:
            try:
                explore.stop_recording()
            except Exception as exc:
                print(f"Could not stop recording cleanly: {exc}")

        if connected:
            try:
                explore.disconnect()
            except Exception as exc:
                print(f"Could not disconnect cleanly: {exc}")

        win.close()
        print(f"Data saved in: {output_dir}")

    core.quit()


if __name__ == "__main__":
    main()