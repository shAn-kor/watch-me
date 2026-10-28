import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router-dom";
import type { ApiClient } from "../api/client";
import { ApiProvider } from "../api/provider";
import type { createAppRouter } from "./router";

export function createQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
  });
}

export interface AppProps {
  router: ReturnType<typeof createAppRouter>;
  queryClient?: QueryClient;
  /** main.tsx passes the http or mock client (VITE_API_MOCK); tests pass a mock client. */
  client: ApiClient;
}

/** Providers shared by main.tsx and tests. AuthProvider joins in lane FE-C. */
export function App({ router, queryClient, client }: AppProps) {
  return (
    <ApiProvider client={client}>
      <QueryClientProvider client={queryClient ?? createQueryClient()}>
        <RouterProvider router={router} />
      </QueryClientProvider>
    </ApiProvider>
  );
}
