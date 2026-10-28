import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "react-router-dom";
import type { createAppRouter } from "./router";

export function createQueryClient() {
  return new QueryClient({
    defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
  });
}

export interface AppProps {
  router: ReturnType<typeof createAppRouter>;
  queryClient?: QueryClient;
}

/** Providers shared by main.tsx and tests. AuthProvider joins in lane FE-C. */
export function App({ router, queryClient }: AppProps) {
  return (
    <QueryClientProvider client={queryClient ?? createQueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}
