Analyze the provided video reel (including visual and audio elements) and any associated metadata. Extract the following information and output it as a valid JSON object matching this exact schema:

{
  "visual_text": "Text extracted from in-video visual textual details",
  "transcript": "Complete Audio transcript of the video",
  "summary": "A short summary under 100 words of what the reel is about and what it says based on the visual_text, transcript and the visual understanding of the video",
  "tags": ["list of 3 to 5 categorical tags/keywords describing the reel perfectly, e.g. #vlog, #infotainment, #entertainment, #tutorial, #trending, #guide, #howto, #cinematic, #storytelling, etc."],
  "location": "Location information if any, otherwise null"
}

Ensure the output is strictly a JSON object and contains no additional formatting, markdown wrappers, or text outside the JSON.
