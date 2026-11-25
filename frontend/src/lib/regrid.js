// Notes on a new beat grid after a BPM or GAP change (docs/architecture/recalculation.md): every note and line break
// stays at its moment in the song; only its beat number changes. Moved here from Step4Editor so it can be tested.
//
// A grid is { bpm, gapMs }: beat 0 is at gapMs, one beat is 15000 / bpm ms (Ultrastar BPM is 4× the musical tempo).
// rawTimings are the syllable timings the editor keeps besides the notes (start/end in seconds, plus beatAtBpm,
// durationAtBpm, syncedBpm), one per note, in order.

/** The moment (ms in the song) of `beat` on `grid`. */
export function msOfBeat(beat, grid) {
  return grid.gapMs + beat * 15000 / grid.bpm;
}

/** The beat (not rounded) at `ms` on `grid`. */
export function beatOfMs(ms, grid) {
  return (ms - grid.gapMs) * grid.bpm / 15000;
}

/** rawTimings matching the notes as they are now on `grid` (a copy). A timing without a note keeps its values. */
export function syncTimings(rawTimings, notes, grid) {
  if (!rawTimings?.length) return rawTimings || [];
  const gapSec = grid.gapMs / 1000;
  const nonBreakNotes = notes.filter(n => n.type !== 'break');
  return rawTimings.map((timing, i) => {
    const note = nonBreakNotes[i];
    if (!note) return { ...timing };
    return {
      ...timing,
      start: gapSec + (note.startBeat * 15) / grid.bpm,
      end: gapSec + ((note.startBeat + note.duration) * 15) / grid.bpm,
      // The beat position + BPM, so the next BPM change scales directly (one rounding, no drift)
      beatAtBpm: note.startBeat,
      durationAtBpm: note.duration,
      syncedBpm: grid.bpm,
    };
  });
}

/** Notes and breaks moved from grid `from` to grid `to`, each kept at its moment in the song (the editor without
 * rawTimings). `snap` rounds a beat to the editor's grid. Sorted by beat. */
export function regridNotes(notes, from, to, snap = Math.round) {
  const toBeat = ms => snap(Math.round(beatOfMs(ms, to)));
  return notes.map(n => {
    if (n.type === 'break') {
      const newBeat = toBeat(msOfBeat(n.startBeat, from));
      const newEndBeat = n.endBeat != null ? Math.max(newBeat + 1, toBeat(msOfBeat(n.endBeat, from))) : null;
      return { ...n, startBeat: newBeat, endBeat: newEndBeat };
    }
    const newStart = toBeat(msOfBeat(n.startBeat, from));
    // Duration: scale by BPM ratio (GAP doesn't affect duration in beats)
    const newDuration = Math.max(1, Math.round(n.duration * to.bpm / from.bpm));
    return { ...n, startBeat: newStart, duration: newDuration };
  }).sort((a, b) => a.startBeat - b.startBeat);
}

/**
 * The notes on grid `to` after a BPM or GAP change from grid `from`, built from the rawTimings (the editor with
 * rawTimings). Returns { notes, rawTimings }, or null without rawTimings (then `regridNotes` applies).
 *
 * The rawTimings are first brought up to date with the notes as they are on `from`: they used to be updated only after
 * a mouse drag, so notes moved with the keyboard, pasted or changed by a tool jumped back to where they were before.
 *
 * Options: bpmChanged (a BPM change; else only GAP changed), isDuet, pitchMap (pitch per timing, for notes without
 * one), snap (rounds a beat to the editor's grid).
 */
export function requantize(notes, rawTimings, from, to, { bpmChanged = false, isDuet = false, pitchMap = [], snap = Math.round } = {}) {
  if (!rawTimings?.length) return null;
  const timings = syncTimings(rawTimings, notes, from);
  const currentNotes = notes.filter(n => n.type !== 'break');

  // If notes have been added/split beyond rawTimings count, we cannot safely rebuild from rawTimings (it would discard
  // user-added notes and misalign syllables). Instead, scale all beat positions directly. A duet always scales:
  // rebuilding would lose the singers and push overlapping singers' notes apart.
  if (currentNotes.length !== timings.length || isDuet) {
    let moved;
    if (bpmChanged) {
      // BPM change: GAP stays, so beats scale proportionally
      moved = notes.map(n => {
        const newStartBeat = Math.round(n.startBeat * to.bpm / from.bpm);
        const newDuration = n.type === 'break' ? n.duration : Math.max(1, Math.round((n.duration ?? 1) * to.bpm / from.bpm));
        const newEndBeat = n.endBeat == null ? null : Math.round(n.endBeat * to.bpm / from.bpm);
        return { ...n, startBeat: newStartBeat, duration: newDuration, endBeat: newEndBeat };
      });
    } else {
      // GAP-only change: keep the moments in the song
      moved = notes.map(n => {
        const newStart = Math.round(beatOfMs(msOfBeat(n.startBeat, from), to));
        if (n.type === 'break') {
          const newEnd = n.endBeat == null ? null : Math.max(newStart + 1, Math.round(beatOfMs(msOfBeat(n.endBeat, from), to)));
          return { ...n, startBeat: newStart, endBeat: newEnd };
        }
        return { ...n, startBeat: newStart };
      });
    }
    return { notes: moved, rawTimings: syncTimings(timings, moved, to) };
  }

  // Preserve user edits (syllable, pitch, …): notes and rawTimings are in the same order, one note per timing
  const userEdits = currentNotes.map(cn => ({
    syllable: cn.syllable, pitch: cn.pitch, isRap: cn.isRap, isGolden: cn.isGolden, isFreestyle: cn.isFreestyle,
  }));

  const gapSec = to.gapMs / 1000;
  const beatToTime = beat => gapSec + (beat * 15) / to.bpm;
  // Existing breaks keep their moment in the song: anchored on the old grid, mapped into the new one
  const prevGapSec = from.gapMs / 1000;
  const preservedBreaks = notes.filter(n => n.type === 'break').map(n => {
    const startBeat = Number(n.startBeat) || 0;
    const endBeat = n.endBeat == null ? null : Number(n.endBeat);
    return {
      startSec: prevGapSec + (startBeat * 15) / from.bpm,
      endSec: endBeat == null ? null : prevGapSec + (endBeat * 15) / from.bpm,
    };
  });
  const preserveExistingBreaks = preservedBreaks.length > 0;

  let id = 0;
  let prevLineIndex = null;
  let lastEndBeat = 0;
  const newNotes = [];

  for (let i = 0; i < timings.length; i++) {
    const timing = timings[i];
    const lineIndex = timing.line_index ?? 0;

    // Insert a break between phrases only when there are no existing breaks to preserve
    if (!preserveExistingBreaks && prevLineIndex !== null && lineIndex !== prevLineIndex) {
      const breakStart = lastEndBeat + 2;
      const nextStartBeat = Math.round(((timing.start - gapSec) * to.bpm) / 15);
      const breakEnd = Math.max(breakStart + 1, nextStartBeat - 2);
      if (breakEnd > breakStart) {
        newNotes.push({ id: id++, type: 'break', startBeat: breakStart, endBeat: breakEnd,
          timeMs: beatToTime(breakStart) * 1000, endTimeMs: beatToTime(breakEnd) * 1000 });
      } else {
        newNotes.push({ id: id++, type: 'break', startBeat: breakStart, endBeat: null,
          timeMs: beatToTime(breakStart) * 1000, endTimeMs: null });
      }
    }

    // A BPM change scales the stored beat positions (one rounding, no drift); a GAP change uses seconds, so notes
    // stay at their moments in the song
    let startBeat, duration;
    if (bpmChanged && timing.syncedBpm != null && timing.beatAtBpm != null) {
      startBeat = Math.round(timing.beatAtBpm * to.bpm / timing.syncedBpm);
      duration = Math.max(1, Math.round(timing.durationAtBpm * to.bpm / timing.syncedBpm));
    } else {
      startBeat = Math.round(((timing.start - gapSec) * to.bpm) / 15);
      const endBeat = Math.max(startBeat + 1, Math.round(((timing.end - gapSec) * to.bpm) / 15));
      duration = Math.max(1, endBeat - startBeat);
    }
    let endBeat = startBeat + duration;

    // Prevent overlap with the previous note
    if (startBeat < lastEndBeat && newNotes.some(n => n.type !== 'break')) {
      startBeat = lastEndBeat + 1;
      endBeat = Math.max(startBeat + 1, endBeat);
      duration = endBeat - startBeat;
    }

    const edit = userEdits[i];
    const pitch = edit?.pitch ?? pitchMap[i] ?? 60;
    newNotes.push({
      id: id++,
      startBeat,
      duration,
      pitch,
      syllable: edit?.syllable ?? timing.syllable,
      isRap: edit?.isRap ?? timing.is_rap ?? false,
      isGolden: edit?.isGolden || false,
      isFreestyle: edit?.isFreestyle || false,
      confidence: timing.confidence ?? 1.0,
      original: { startBeat, duration, pitch },
    });

    lastEndBeat = startBeat + duration;
    prevLineIndex = lineIndex;
  }

  if (preserveExistingBreaks) {
    for (const b of preservedBreaks) {
      const startBeat = snap(Math.round(((b.startSec - gapSec) * to.bpm) / 15));
      const endBeat = b.endSec === null ? null
        : Math.max(startBeat + 1, snap(Math.round(((b.endSec - gapSec) * to.bpm) / 15)));
      newNotes.push({ id: id++, type: 'break', startBeat, endBeat,
        timeMs: b.startSec * 1000, endTimeMs: b.endSec != null ? b.endSec * 1000 : null });
    }
  }

  const sorted = newNotes.sort((a, b) => {
    const byBeat = (a.startBeat ?? 0) - (b.startBeat ?? 0);
    if (byBeat !== 0) return byBeat;
    const aBreak = a.type === 'break' ? 0 : 1;
    const bBreak = b.type === 'break' ? 0 : 1;
    if (aBreak !== bBreak) return aBreak - bBreak;
    return (a.id ?? 0) - (b.id ?? 0);
  });
  return { notes: sorted, rawTimings: syncTimings(timings, sorted, to) };
}
