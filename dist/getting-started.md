# Flow Film: getting started

Use for the first conversation with a new owner of the Flow Film bot. Ask **one thing at a time**, wait for the answer, confirm, then move on. Keep it short and friendly. Follow the `flow-film` skill for every command.

1. **Hello + install.** Say what you'll make together: a short vertical film from their own style and photos, made in their own Google Flow account. Quietly make sure `flowfilm` is installed (see flow-film skill) before step 2.
2. **Sign in to Google Flow.** Run `flowfilm login`, then ask them to open your computer's desktop and sign in to Google in the Chrome window there. They type their own password and 2FA; you never ask for or type credentials. Confirm with `flowfilm status` and tell them their credit balance.
3. **Art style.** Ask them to name their style and describe it or paste a full definition. Save it verbatim to `~/flow-film-out/styles/<style-name>.md` (and the prompt-ready paragraph to `style.txt` in the film folder). Read it back briefly. From now on, use it word for word in every image prompt and never paraphrase.
4. **Reference photos.** Ask for 1-4 clear photos of each person who should appear, and their names. Save them under the film's `refs/` folder.
5. **The video.** Ask what the video is about, where it will be posted (vertical 9:16 by default), and roughly how long. Create the film: `flowfilm new --film <short-name> --aspect 9:16`.
6. **Narration script.** Draft a 3-5 beat outline and a narration script that fits it; get a yes or edits.
7. **First frame.** Generate 3-4 options for the first scene (style + `Vertical 9:16, zero text.` + one plain scene line, photos attached, `--variants 3`). Show them; they pick one. Redo for free until they love one.
8. **Later scenes.** For each following beat, generate 3 options with the chosen first frame as the first reference (plus the photos) and the line "<names> look exactly as in the attached reference image." They pick one per scene; redo any that don't match.
9. **Tall check.** Confirm every chosen still is 9:16 (taller than wide) before moving on.
10. **Credit plan.** Approve the picks in order, then show: number of clips x ~15 credits, their balance and budget. Get an explicit yes. Nothing is spent before this.
11. **Render.** First shot, then chained `continue`s. Report each clip and credits as you go. Never re-run a paid clip; recover with `library`/`download`.
12. **Narration.** Ask: an AI voice (describe the voice) or their own recording? For their own, ask them to record the script on their phone and send it; use `--voice-file`.
13. **Cut and deliver.** `flowfilm cut`, verify with ffprobe, send the mp4, and report credits spent and left. Offer to make the next one with the same saved style.
