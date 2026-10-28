import type { ReactNode } from "react";
import {
  createBrowserRouter,
  createMemoryRouter,
  Outlet,
  type RouteObject,
} from "react-router-dom";
import ConsentPage from "../routes/creator/ConsentPage";
import DogDetailPage from "../routes/creator/DogDetailPage";
import DogListPage from "../routes/creator/DogListPage";
import DogNewPage from "../routes/creator/DogNewPage";
import LoginPage from "../routes/creator/LoginPage";
import ReviewPage from "../routes/creator/ReviewPage";
import SessionNewPage from "../routes/creator/SessionNewPage";
import SessionPage from "../routes/creator/SessionPage";
import NotAvailablePage from "../routes/public/NotAvailablePage";
import PublicProfilePage from "../routes/public/PublicProfilePage";
import TermsPage from "../routes/TermsPage";
import {
  RedirectIfAuthed,
  RequireConsent,
  RequireMember,
} from "./guards";

function Shell() {
  return (
    <main>
      <Outlet />
    </main>
  );
}

function member(page: ReactNode) {
  return <RequireMember>{page}</RequireMember>;
}

/** Needs a signed-in member who accepted the consent notice (ORG-4). */
function consented(page: ReactNode) {
  return (
    <RequireMember>
      <RequireConsent>{page}</RequireConsent>
    </RequireMember>
  );
}

/** Route table of 06 section 6.1. */
export const routes: RouteObject[] = [
  {
    element: <Shell />,
    children: [
      {
        path: "/app/login",
        element: (
          <RedirectIfAuthed>
            <LoginPage />
          </RedirectIfAuthed>
        ),
      },
      { path: "/app/consent", element: member(<ConsentPage />) },
      { path: "/app", element: consented(<DogListPage />) },
      { path: "/app/dogs/new", element: consented(<DogNewPage />) },
      { path: "/app/dogs/:dogId", element: consented(<DogDetailPage />) },
      {
        path: "/app/dogs/:dogId/sessions/new",
        element: consented(<SessionNewPage />),
      },
      { path: "/app/sessions/:sessionId", element: consented(<SessionPage />) },
      {
        path: "/app/sessions/:sessionId/review",
        element: consented(<ReviewPage />),
      },
      { path: "/d/:slug", element: <PublicProfilePage /> },
      { path: "/terms", element: <TermsPage /> },
      // No index or search page (FE-PUB-11): everything else is "not available".
      { path: "*", element: <NotAvailablePage /> },
    ],
  },
];

export function createAppRouter() {
  return createBrowserRouter(routes);
}

export function createTestRouter(initialEntries: string[] = ["/"]) {
  return createMemoryRouter(routes, { initialEntries });
}
