"""Our own camera-move phrases, appended to shot prompts."""
MOVES = {
    "push-in": "slow steady dolly push toward the subject",
    "pull-out": "camera eases backward, revealing the wider surroundings",
    "orbit": "camera circles the subject in a smooth half orbit",
    "full-orbit": "camera makes a complete smooth 360 degree circle around the subject",
    "crane-up": "camera rises vertically, tilting down to keep the subject in frame",
    "crane-down": "camera descends from high above to eye level",
    "drone-glide": "high aerial glide forward over the landscape",
    "flythrough": "camera flies forward through the scene, passing close to objects",
    "snap-zoom": "sudden fast zoom onto the subject's face",
    "vertigo": "dolly zoom: background stretches while the subject stays the same size",
    "pan-left": "slow horizontal pan from right to left",
    "pan-right": "slow horizontal pan from left to right",
    "tilt-up": "camera tilts upward from the ground to the sky",
    "handheld": "slightly shaky handheld documentary feel following the action",
    "tracking": "camera tracks alongside the subject as it moves",
    "follow": "camera follows behind the subject at shoulder height",
    "low-hero": "low angle looking up, slow push, heroic framing",
    "top-down": "overhead bird's-eye view, slowly rotating",
    "static": "locked-off tripod shot, no camera movement",
    "rack-focus": "focus shifts from the foreground to the background subject",
    "whip-pan": "fast whip pan blurring into the next view",
    "parallax": "slow sideways slide with strong foreground parallax",
    "space-to-ground": "starts in orbit above Earth and dives continuously down to street level",
    "loop": "motion ends exactly where it began so the clip loops seamlessly",
    "reveal-title": "camera settles on empty space in the frame, leaving room for a title",
}


def apply(prompt, move=None):
    if not move:
        return prompt
    if move not in MOVES:
        raise KeyError(f"unknown move '{move}'. Options: {', '.join(MOVES)}")
    return f"{prompt.rstrip('. ')}. Camera: {MOVES[move]}."
