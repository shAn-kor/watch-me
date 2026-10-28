import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { createHttpClient } from "./api/client";
import { createMockClient } from "./api/mock";
import { App } from "./app/App";
import { createAppRouter } from "./app/router";

// VITE_API_MOCK=1 selects MockTransport (06 section 6.2).
const client =
  import.meta.env.VITE_API_MOCK === "1"
    ? createMockClient()
    : createHttpClient();

const root = document.getElementById("root");
if (!root) throw new Error("#root not found");

createRoot(root).render(
  <StrictMode>
    <App router={createAppRouter()} client={client} />
  </StrictMode>,
);
