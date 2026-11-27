/** Turn provider and limit errors into something a visitor can act on. */
export function friendlyError(message: string): string {
  if (/daily limit|429|quota|too many/i.test(message))
    return "Live questions are paused: the free model quota or today’s limit for this demo is used up. The example questions still work.";
  if (/503|502|unavailable|high demand|unreachable|timed? ?out/i.test(message))
    return "The model is busy right now. Try again in a minute, or use one of the example questions.";
  if (/not indexed/i.test(message)) return "This repository was removed to free up space. Go back and open it again.";
  if (/not configured/i.test(message)) return "Live questions are not set up on this deployment. The example questions still work.";
  return message;
}

