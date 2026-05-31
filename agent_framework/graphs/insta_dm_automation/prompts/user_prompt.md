Analyze the provided video reel (including visual and audio elements) and any associated metadata. Extract the following information and output it as a valid JSON object matching this exact schema:

{
  "tags": ["list of 3 to 5 categorical tags/keywords describing the reel perfectly, e.g. #vlog, #infotainment, #entertainment, #tutorial, #trending, #guide, #howto, #cinematic, #storytelling, etc."],
  "extracted_text": "Text extracted from in-video visual text, spoken audio, and from any provided metadata.",
  "summary": "A short summary under 100 words of what the reel is about and what it says.",
  "location": "Location information if any, otherwise null"
}

Ensure the output is strictly a JSON object and contains no additional formatting, markdown wrappers, or text outside the JSON.
