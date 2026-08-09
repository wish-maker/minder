/** Best-effort OpenWebUI link: same host this page is served from, port 8080
 * (the compose default) -- not hardcoded to "localhost", which broke on any
 * non-local deployment (hantal, the Pi, a real domain). */
export const openWebUiUrl =
  typeof window !== "undefined"
    ? `http://${window.location.hostname}:8080`
    : "http://localhost:8080";
