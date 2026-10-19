"""Test: full MFA alignment via the alignment service."""
import sys
sys.path.insert(0, '.')

from services.alignment import align_lyrics_to_audio

vocals_path = "uploads/be3676fb/U2 - Beautiful Day_vocals.mp3"

# First verse lyrics (hyphenated)
lyrics = """The heart is a bloom
Shoots up through the sto-ny ground
But there's no room
No space to rent in this town
You're out of luck
And the rea-son that you had to care
The traf-fic is stuck
And you're not mov-ing a-ny-where"""

print("Running MFA alignment on Beautiful Day vocals...")
results = align_lyrics_to_audio(vocals_path, lyrics)

print(f"\n=== RESULTS: {len(results)} syllables ===")
print(f"{'#':<4} {'Syllable':<15} {'Start':>8} {'End':>8} {'Dur':>6} {'Conf':>5} {'Method':<20}")
print("-" * 72)
for i, r in enumerate(results):
    dur = r['end'] - r['start']
    print(f"{i:<4} {r['syllable']:<15} {r['start']:>8.2f} {r['end']:>8.2f} {dur:>6.2f} {r['confidence']:>5.2f} {r.get('method', '?'):<20}")

# Compare "the" start time with reference GAP (13208ms = 13.208s)
if results:
    first_start = results[0]['start']
    ref_gap = 13.208  # from reference Ultrastar file
    print(f"\nFirst syllable starts at: {first_start:.3f}s")
    print(f"Reference GAP:            {ref_gap:.3f}s")
    print(f"Difference:               {(first_start - ref_gap)*1000:.0f}ms")
    
    last_end = results[-1]['end']
    print(f"\nLast syllable ends at:    {last_end:.2f}s")
    print(f"Total lyrics span:        {last_end - first_start:.2f}s")
