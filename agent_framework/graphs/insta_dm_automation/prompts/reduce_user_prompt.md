Synthesize the following segment analyses into a single coherent analysis of the complete video.

## Video Metadata
{video_metadata}

## Segment Analyses
{chunk_analyses}

## Required Output Schema
Produce a single JSON object with exactly these fields:

{
  "visual_text": "All unique on-screen text merged chronologically from all segments",
  "transcript": "Complete merged audio transcript as one continuous passage",
  "summary": "A new cohesive summary under 100 words synthesizing the entire video",
  "tags": ["3 to 5 tags representing the overall video content"],
  "location": "Most confident location from any segment, or null"
}

Ensure the output is strictly a JSON object and contains no additional formatting, markdown wrappers, or text outside the JSON.
