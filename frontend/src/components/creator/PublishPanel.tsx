import { useQueryClient } from "@tanstack/react-query";
import { useId, useState } from "react";
import { useNavigate } from "react-router-dom";
import { isApiError } from "../../api/errors";
import { useApi } from "../../api/provider";
import type { ChecklistMissing, DogDetailResponse } from "../../api/types";
import { ConfirmDialog } from "./Dialog";
import { absoluteUrl, formatInstant } from "./format";
import { ErrorNotice, type ErrorTable } from "./errors";
import { PUBLISH_MISSING_LABEL } from "./constants";
import { useToast } from "./Toast";
import { BlockedButton } from "./ui";

type DialogKind =
  "publish" | "unpublish" | "reopen" | "adopt" | "delete" | null;

const ERRORS: ErrorTable = {
  forbidden_role: "Only staff can do this.",
  not_found: "This dog was not found. It may have been deleted.",
};

function missingText(list: ChecklistMissing[] | undefined): string {
  return (list ?? []).map((m) => PUBLISH_MISSING_LABEL[m]).join(", ");
}

interface Form {
  people: boolean;
  concerns: string;
  none: boolean;
}

/** Publish, unpublish, adopted and delete controls of S5 (05 section 5). */
export function PublishPanel({
  data,
  isStaff,
}: {
  data: DogDetailResponse;
  isStaff: boolean;
}) {
  const api = useApi();
  const qc = useQueryClient();
  const toast = useToast();
  const navigate = useNavigate();
  const { dog, checklist } = data;
  const id = useId();

  const [edited, setEdited] = useState<Form | null>(null);
  const [dialog, setDialog] = useState<DialogKind>(null);
  const [busy, setBusy] = useState(false);
  const [typed, setTyped] = useState("");
  const [failure, setFailure] = useState<unknown>(null);
  const [failureTable, setFailureTable] = useState<ErrorTable>(ERRORS);
  const [notice, setNotice] = useState<string | null>(null);

  const saved: Form = {
    people: checklist.people_check,
    concerns: checklist.known_concerns ?? "",
    none: checklist.known_concerns_none,
  };
  const form = edited ?? saved;
  const dirty =
    edited !== null &&
    (edited.people !== saved.people ||
      edited.concerns !== saved.concerns ||
      edited.none !== saved.none);

  const refresh = async () => {
    await Promise.all([
      qc.invalidateQueries({ queryKey: ["dog", dog.id] }),
      qc.invalidateQueries({ queryKey: ["dogs"] }),
    ]);
  };

  const fail = (e: unknown, table: ErrorTable) => {
    setFailureTable({ ...ERRORS, ...table });
    setFailure(e);
  };

  const saveChecklist = async () => {
    setBusy(true);
    setFailure(null);
    setNotice(null);
    try {
      const text = form.concerns.trim();
      const r = await api.saveChecklist(dog.id, {
        people_check: form.people,
        known_concerns: form.none || text === "" ? null : text,
        known_concerns_none: form.none,
      });
      qc.setQueryData<DogDetailResponse>(["dog", dog.id], (old) =>
        old ? { ...old, checklist: r.checklist } : old,
      );
      setEdited(null);
      toast.success("Checklist saved.");
    } catch (e) {
      fail(e, {
        forbidden_role: "Only staff can change the checklist.",
        invalid_state:
          "The checklist cannot change now. Unpublish the dog first.",
        validation_error: (err) => {
          const fields = isApiError(err) ? (err.details.fields ?? []) : [];
          return fields.some((f) => f.problem === "too_long")
            ? "Known concerns can have 1,000 characters at most."
            : "Clear the text, or untick None known.";
        },
      });
    } finally {
      setBusy(false);
    }
  };

  const run = async (
    action: () => Promise<unknown>,
    success: string,
    table: ErrorTable,
    after?: () => void,
  ) => {
    setBusy(true);
    setFailure(null);
    setNotice(null);
    try {
      await action();
      setDialog(null);
      setTyped("");
      toast.success(success);
      if (after) after();
      else await refresh();
    } catch (e) {
      setDialog(null);
      if (isApiError(e) && e.code === "publish_checklist_incomplete") {
        setNotice(
          `Cannot publish yet. Still needed: ${missingText(e.details.missing)}.`,
        );
        await refresh();
      } else if (
        isApiError(e) &&
        e.code === "not_found" &&
        table.not_found === "deleted"
      ) {
        toast.error("This dog was already deleted.");
        navigate("/app/dogs");
      } else {
        fail(e, table);
      }
    } finally {
      setBusy(false);
    }
  };

  const publish = () =>
    run(() => api.publishDog(dog.id), "Published. The link works now.", {
      forbidden_role: "Only staff can publish.",
      invalid_state: "This dog is not a draft anymore. Reload the page.",
    });
  const unpublish = () =>
    run(
      () => api.unpublishDog(dog.id),
      "Unpublished. The link no longer works.",
      {
        forbidden_role: "Only staff can unpublish.",
        invalid_state: "This dog is not published or adopted. Reload the page.",
      },
    );
  const reopen = () =>
    run(() => api.unpublishDog(dog.id), "Reopened as draft.", {
      forbidden_role: "Only staff can unpublish.",
      invalid_state: "This dog is not published or adopted. Reload the page.",
    });
  const adopt = () =>
    run(() => api.markAdopted(dog.id), "Marked as adopted.", {
      forbidden_role: "Only staff can mark a dog as adopted.",
      invalid_state:
        "This dog cannot be marked as adopted now. Reload the page.",
    });
  const remove = () =>
    run(
      () => api.deleteDog(dog.id),
      `Deleting ${dog.name}. Files are being removed.`,
      {
        forbidden_role: "Only staff can delete a dog.",
        not_found: "deleted",
      },
      () => {
        navigate("/app/dogs");
        void qc.invalidateQueries({ queryKey: ["dogs"] });
      },
    );

  const missing = checklist.missing;
  const canPublish =
    isStaff && dog.status === "draft" && checklist.ready_to_publish && !dirty;
  const missingId = `${id}-missing`;
  const nameMatches =
    typed.trim().toLowerCase() === dog.name.trim().toLowerCase();

  const checklistLocked = dog.status !== "draft";

  return (
    <section aria-labelledby={`${id}-h`}>
      <h2 id={`${id}-h`}>Publish</h2>

      {notice ? (
        <div className="wm-notice" role="alert">
          <p>{notice}</p>
        </div>
      ) : null}
      {failure ? <ErrorNotice error={failure} table={failureTable} /> : null}

      {dog.status === "published" ? (
        <div className="wm-stack">
          <p className="wm-strong">
            Published {dog.published_at ? formatInstant(dog.published_at) : ""}
          </p>
          {dog.public_path ? <p>{absoluteUrl(dog.public_path)}</p> : null}
          <div className="wm-row">
            <button
              type="button"
              className="wm-btn wm-btn--secondary"
              onClick={() => {
                const url = dog.public_path ? absoluteUrl(dog.public_path) : "";
                void navigator.clipboard
                  ?.writeText(url)
                  .then(() => toast.success("Link copied."))
                  .catch(() =>
                    toast.error(
                      "Could not copy the link. Select it and copy by hand.",
                    ),
                  );
              }}
            >
              Copy link
            </button>
            {dog.public_path ? (
              <a
                className="wm-btn wm-btn--secondary"
                href={dog.public_path}
                target="_blank"
                rel="noreferrer"
              >
                Open public page
              </a>
            ) : null}
          </div>
          {isStaff ? (
            <div className="wm-row">
              <button
                type="button"
                className="wm-btn wm-btn--secondary"
                onClick={() => setDialog("unpublish")}
              >
                Unpublish
              </button>
              <button
                type="button"
                className="wm-btn wm-btn--secondary"
                onClick={() => setDialog("adopt")}
              >
                Mark as adopted
              </button>
            </div>
          ) : null}
        </div>
      ) : dog.status === "adopted" ? (
        <div className="wm-stack">
          <p>
            Marked as adopted on{" "}
            {dog.adopted_at ? formatInstant(dog.adopted_at) : ""}. The profile
            is hidden. Clips are kept.
          </p>
          {isStaff ? (
            <button
              type="button"
              className="wm-btn wm-btn--secondary"
              onClick={() => setDialog("reopen")}
            >
              Reopen as draft
            </button>
          ) : null}
        </div>
      ) : isStaff ? (
        <form
          className="wm-stack"
          onSubmit={(e) => {
            e.preventDefault();
            if (dirty && !busy) void saveChecklist();
          }}
        >
          <fieldset className="wm-field">
            <legend>Before you publish</legend>
            {checklist.people_check_at && !checklist.people_check ? (
              <p className="wm-notice">
                A clip was added after the last check. Check all clips again.
              </p>
            ) : null}
            <div className="wm-check">
              <input
                id={`${id}-people`}
                type="checkbox"
                checked={form.people}
                aria-describedby={`${id}-people-help`}
                disabled={checklistLocked}
                onChange={(e) =>
                  setEdited({ ...form, people: e.target.checked })
                }
              />
              <label htmlFor={`${id}-people`}>
                No one other than consenting members appears in any clip of this
                dog.
              </label>
            </div>
            <p id={`${id}-people-help`} className="wm-help">
              Check the whole clip, not only the cited part. Visitors can play
              the full clip.
            </p>
            <div className="wm-field">
              <label htmlFor={`${id}-concerns`}>Known concerns</label>
              <textarea
                id={`${id}-concerns`}
                value={form.none ? "" : form.concerns}
                disabled={form.none || checklistLocked}
                onChange={(e) =>
                  setEdited({ ...form, concerns: e.target.value, none: false })
                }
              />
            </div>
            <div className="wm-check">
              <input
                id={`${id}-none`}
                type="checkbox"
                checked={form.none}
                disabled={checklistLocked}
                onChange={(e) =>
                  setEdited({
                    ...form,
                    none: e.target.checked,
                    concerns: e.target.checked ? "" : form.concerns,
                  })
                }
              />
              <label htmlFor={`${id}-none`}>None known</label>
            </div>
            <p className="wm-muted">
              Confirmed facts: {checklist.confirmed_fact_count} confirmed
            </p>
          </fieldset>
          {missing.length > 0 ? (
            <div id={missingId}>
              <p>Still needed to publish:</p>
              <ul>
                {missing.map((m) => (
                  <li key={m}>{PUBLISH_MISSING_LABEL[m]}</li>
                ))}
              </ul>
            </div>
          ) : dirty ? (
            <p id={missingId}>Save the checklist before you publish.</p>
          ) : null}
          <div className="wm-row">
            <button
              type="submit"
              className="wm-btn wm-btn--secondary"
              disabled={!dirty || busy}
            >
              Save checklist
            </button>
            <BlockedButton
              blocked={!canPublish || busy}
              describedBy={missing.length > 0 || dirty ? missingId : undefined}
              onClick={() => setDialog("publish")}
            >
              Publish
            </BlockedButton>
          </div>
        </form>
      ) : (
        <div className="wm-stack">
          <ul>
            <li>
              People check: {checklist.people_check ? "done" : "not done"}
            </li>
            <li>
              Known concerns:{" "}
              {checklist.known_concerns_none
                ? "none known"
                : checklist.known_concerns
                  ? "written"
                  : "not done"}
            </li>
            <li>{checklist.confirmed_fact_count} confirmed</li>
          </ul>
          <p>Only staff can publish.</p>
        </div>
      )}

      {isStaff && dog.status !== "adopted" ? (
        <div className="wm-stack" style={{ marginTop: 24 }}>
          <h2>Danger zone</h2>
          <div className="wm-row">
            {dog.status === "draft" ? (
              <button
                type="button"
                className="wm-btn wm-btn--danger"
                onClick={() => setDialog("adopt")}
              >
                Mark as adopted
              </button>
            ) : null}
            <button
              type="button"
              className="wm-btn wm-btn--danger"
              onClick={() => setDialog("delete")}
            >
              Delete dog
            </button>
          </div>
        </div>
      ) : null}
      {isStaff && dog.status === "adopted" ? (
        <div className="wm-stack" style={{ marginTop: 24 }}>
          <h2>Danger zone</h2>
          <div className="wm-row">
            <button
              type="button"
              className="wm-btn wm-btn--danger"
              onClick={() => setDialog("delete")}
            >
              Delete dog
            </button>
          </div>
        </div>
      ) : null}

      {dialog === "publish" ? (
        <ConfirmDialog
          title={`Publish ${dog.name}?`}
          confirmLabel="Publish"
          busy={busy}
          onConfirm={() => void publish()}
          onCancel={() => setDialog(null)}
        >
          <p>
            Anyone with the link can watch the clips that confirmed facts use.
            The public page plays only the cited part, but anyone with a
            clip&apos;s link can play the whole clip. Check every whole clip
            before you publish. You can unpublish at any time.
          </p>
        </ConfirmDialog>
      ) : null}
      {dialog === "unpublish" ? (
        <ConfirmDialog
          title={`Unpublish ${dog.name}?`}
          confirmLabel="Unpublish"
          busy={busy}
          onConfirm={() => void unpublish()}
          onCancel={() => setDialog(null)}
        >
          <p>
            The public link stops working right away. Nothing is deleted.
            Publishing again restores the same link.
          </p>
        </ConfirmDialog>
      ) : null}
      {dialog === "reopen" ? (
        <ConfirmDialog
          title={`Reopen ${dog.name}?`}
          confirmLabel="Reopen as draft"
          busy={busy}
          onConfirm={() => void reopen()}
          onCancel={() => setDialog(null)}
        >
          <p>
            The dog goes back to draft. It stays hidden until you publish it
            again.
          </p>
        </ConfirmDialog>
      ) : null}
      {dialog === "adopt" ? (
        <ConfirmDialog
          title={`Mark ${dog.name} as adopted?`}
          confirmLabel="Mark as adopted"
          busy={busy}
          onConfirm={() => void adopt()}
          onCancel={() => setDialog(null)}
        >
          <p>
            The public profile is hidden. Clips and facts are kept. You can
            reopen the dog later.
          </p>
        </ConfirmDialog>
      ) : null}
      {dialog === "delete" ? (
        <ConfirmDialog
          title={`Delete ${dog.name}?`}
          confirmLabel="Delete dog"
          danger
          busy={busy}
          confirmDisabled={!nameMatches}
          onConfirm={() => void remove()}
          onCancel={() => {
            setDialog(null);
            setTyped("");
          }}
        >
          <p>
            This removes the dog, its clips, and its facts from storage. It
            cannot be undone. Copies that someone already downloaded cannot be
            recalled. Type the dog&apos;s name to confirm.
          </p>
          <input
            type="text"
            aria-label={`Type ${dog.name} to confirm`}
            value={typed}
            autoComplete="off"
            onChange={(e) => setTyped(e.target.value)}
          />
        </ConfirmDialog>
      ) : null}
    </section>
  );
}
