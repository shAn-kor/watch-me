import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState, type FormEvent } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { isApiError } from "../../api/errors";
import { useApi } from "../../api/provider";
import type { Dog, DogSex, DogSize, UpdateDogRequest } from "../../api/types";
import { ConfirmDialog } from "../../components/creator/Dialog";
import { ErrorNotice, globalText } from "../../components/creator/errors";
import { SEX_LABEL, SIZE_LABEL } from "../../components/creator/format";
import { MAX_PHOTO_BYTES } from "../../components/creator/constants";
import { useToast } from "../../components/creator/Toast";
import {
  Field,
  Loading,
  RadioGroup,
  Screen,
} from "../../components/creator/ui";
import { useEnsureAuth } from "../../state/AuthProvider";

const PHOTO_TYPES = ["image/jpeg", "image/png", "image/heic"];
const TYPE_TEXT = "This photo type is not supported. Use JPEG, PNG, or HEIC.";
const SIZE_TEXT = "This photo is larger than 8 MB. Choose a smaller photo.";

function photoErrorText(e: unknown): string {
  if (isApiError(e)) {
    if (e.code === "file_too_large") return SIZE_TEXT;
    if (e.code === "unsupported_file_type") return TYPE_TEXT;
  }
  return globalText(e);
}

interface Form {
  name: string;
  sex: DogSex | "";
  age: string;
  size: DogSize | "";
  location: string;
}

const EMPTY: Form = { name: "", sex: "", age: "", size: "", location: "" };

function fromDog(d: Dog): Form {
  return {
    name: d.name,
    sex: d.sex,
    age: d.age_estimate,
    size: d.size,
    location: d.location ?? "",
  };
}

type Errors = Partial<Record<keyof Form, string>>;

function validate(f: Form): Errors {
  const e: Errors = {};
  const name = f.name.trim();
  if (name.length < 1 || name.length > 60)
    e.name = "Enter a name of 1 to 60 characters.";
  if (!f.sex) e.sex = "Choose one option.";
  const age = f.age.trim();
  if (age.length < 1 || age.length > 40)
    e.age = "Enter an age estimate of 1 to 40 characters.";
  if (!f.size) e.size = "Choose one option.";
  if (f.location.trim().length > 120)
    e.location = "Use 120 characters or fewer.";
  return e;
}

function serverErrors(e: unknown): Errors | null {
  if (!isApiError(e) || e.code !== "validation_error") return null;
  const out: Errors = {};
  for (const f of e.details.fields ?? []) {
    if (f.path.endsWith("name"))
      out.name = "Enter a name of 1 to 60 characters.";
    else if (f.path.endsWith("age_estimate"))
      out.age = "Enter an age estimate of 1 to 40 characters.";
    else if (f.path.endsWith("sex")) out.sex = "Choose one option.";
    else if (f.path.endsWith("size")) out.size = "Choose one option.";
    else if (f.path.endsWith("location"))
      out.location = "Use 120 characters or fewer.";
  }
  return Object.keys(out).length > 0 ? out : null;
}

/** S4 Dog create and edit (05 section 5). */
export default function DogNewPage() {
  const { dogId } = useParams();
  return <DogForm key={dogId ?? "new"} dogId={dogId} />;
}

function DogForm({ dogId }: { dogId: string | undefined }) {
  const api = useApi();
  const auth = useEnsureAuth();
  const qc = useQueryClient();
  const navigate = useNavigate();
  const toast = useToast();
  const location = useLocation();
  const editing = dogId !== undefined;
  const carried =
    (location.state as { photoError?: string } | null)?.photoError ?? null;

  const q = useQuery({
    queryKey: ["dog", dogId],
    queryFn: () => api.getDog(dogId as string),
    enabled: editing && auth.status === "authed",
  });

  // The form starts from the server dog; edits live in `draft` until the first keystroke.
  const [draft, setDraft] = useState<Form | null>(editing ? null : EMPTY);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [photoError, setPhotoError] = useState<string | null>(carried);
  const [errors, setErrors] = useState<Errors>({});
  const [failure, setFailure] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [discard, setDiscard] = useState(false);
  const [submits, setSubmits] = useState(0);
  const formRef = useRef<HTMLFormElement>(null);

  const dog = q.data?.dog ?? null;
  const base: Form = dog ? fromDog(dog) : EMPTY;
  const form = draft ?? base;
  const dirty = editing
    ? file !== null ||
      form.name !== base.name ||
      form.sex !== base.sex ||
      form.age !== base.age ||
      form.size !== base.size ||
      form.location !== base.location
    : file !== null ||
      form.name !== "" ||
      form.sex !== "" ||
      form.age !== "" ||
      form.size !== "" ||
      form.location !== "";

  const set = (patch: Partial<Form>) => setDraft({ ...form, ...patch });

  useEffect(() => {
    return () => {
      if (preview && typeof URL.revokeObjectURL === "function")
        URL.revokeObjectURL(preview);
    };
  }, [preview]);

  useEffect(() => {
    if (submits === 0) return;
    formRef.current
      ?.querySelector<HTMLElement>('[aria-invalid="true"]')
      ?.focus();
  }, [submits]);

  const pickPhoto = (f: File | undefined) => {
    if (!f) return;
    if (f.type && !PHOTO_TYPES.includes(f.type)) {
      setPhotoError(TYPE_TEXT);
      return;
    }
    if (f.size > MAX_PHOTO_BYTES) {
      setPhotoError(SIZE_TEXT);
      return;
    }
    setPhotoError(null);
    setFile(f);
    setPreview(
      typeof URL.createObjectURL === "function" ? URL.createObjectURL(f) : null,
    );
  };

  const backTo = editing ? `/app/dogs/${dogId}` : "/app/dogs";

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (busy) return;
    const found = validate(form);
    setErrors(found);
    setFailure(null);
    if (Object.keys(found).length > 0) {
      setSubmits((n) => n + 1);
      return;
    }
    setBusy(true);
    try {
      const location = form.location.trim();
      let saved: Dog;
      if (editing && dog) {
        const body: UpdateDogRequest = {};
        if (form.name.trim() !== dog.name) body.name = form.name.trim();
        if (form.sex !== dog.sex) body.sex = form.sex as DogSex;
        if (form.age.trim() !== dog.age_estimate)
          body.age_estimate = form.age.trim();
        if (form.size !== dog.size) body.size = form.size as DogSize;
        if (location !== (dog.location ?? ""))
          body.location = location === "" ? null : location;
        saved =
          Object.keys(body).length > 0
            ? (await api.updateDog(dog.id, body)).dog
            : dog;
      } else {
        saved = (
          await api.createDog({
            name: form.name.trim(),
            sex: form.sex as DogSex,
            age_estimate: form.age.trim(),
            size: form.size as DogSize,
            location: location === "" ? null : location,
          })
        ).dog;
      }
      if (file) {
        try {
          await api.uploadDogPhoto(saved.id, file);
        } catch (err) {
          void qc.invalidateQueries({ queryKey: ["dogs"] });
          void qc.invalidateQueries({ queryKey: ["dog", saved.id] });
          toast.error("Dog saved. The photo was not uploaded.");
          navigate(`/app/dogs/${saved.id}/edit`, {
            replace: true,
            state: { photoError: photoErrorText(err) },
          });
          return;
        }
      }
      void qc.invalidateQueries({ queryKey: ["dogs"] });
      void qc.invalidateQueries({ queryKey: ["dog", saved.id] });
      toast.success("Dog saved.");
      navigate(`/app/dogs/${saved.id}`);
    } catch (err) {
      setBusy(false);
      const fields = serverErrors(err);
      if (fields) {
        setErrors(fields);
        setSubmits((n) => n + 1);
      } else {
        setFailure(err);
      }
    }
  };

  const title = editing ? "Edit dog" : "Add dog";
  const goBack = () => {
    if (dirty) setDiscard(true);
    else navigate(backTo);
  };

  if (editing && q.isError) {
    return (
      <Screen title={title} backTo={backTo}>
        <ErrorNotice
          error={q.error}
          table={{
            not_found: "This dog was not found. It may have been deleted.",
          }}
          backLink
          onRetry={
            isApiError(q.error) && q.error.code === "not_found"
              ? undefined
              : () => void q.refetch()
          }
        />
      </Screen>
    );
  }
  if (editing && !dog) {
    return (
      <Screen title={title} backTo={backTo}>
        <Loading text="Loading dog..." onRetry={() => void q.refetch()} />
      </Screen>
    );
  }

  const shownPhoto = preview ?? dog?.photo_url ?? null;
  const hasPhoto = file !== null || Boolean(dog?.photo_url);

  return (
    <Screen
      title={title}
      onBack={goBack}
      action={
        <button
          type="submit"
          form="dog-form"
          className="wm-btn"
          disabled={busy || (editing && !dirty)}
        >
          {busy ? "Saving..." : "Save dog"}
        </button>
      }
    >
      <h1>{title}</h1>
      {editing && dog?.status === "published" ? (
        <p className="wm-notice">
          This dog is published. Changes to the header show on the public
          profile right away.
        </p>
      ) : null}
      {failure ? (
        <ErrorNotice
          error={failure}
          table={{
            not_found: "This dog was not found. It may have been deleted.",
          }}
          backLink={isApiError(failure) && failure.code === "not_found"}
        />
      ) : null}
      <form id="dog-form" ref={formRef} onSubmit={submit} noValidate>
        <div className="wm-field">
          <p className="wm-label">Photo</p>
          {shownPhoto ? (
            <img src={shownPhoto} alt="" className="wm-photo wm-photo--lg" />
          ) : null}
          <div>
            <label className="wm-btn wm-btn--secondary wm-file-btn">
              {hasPhoto ? "Change photo" : "Choose photo"}
              <input
                type="file"
                accept="image/jpeg,image/png,image/heic"
                className="wm-visually-hidden"
                onChange={(e) => {
                  pickPhoto(e.target.files?.[0]);
                  e.target.value = "";
                }}
              />
            </label>
          </div>
          <p className="wm-help">
            JPEG, PNG, or HEIC, up to 8 MB. Location data is removed from
            photos.
          </p>
          {photoError ? <p className="wm-error-text">{photoError}</p> : null}
        </div>
        <Field label="Name" error={errors.name}>
          {({ id, describedBy, invalid }) => (
            <input
              id={id}
              type="text"
              value={form.name}
              aria-invalid={invalid}
              aria-describedby={describedBy}
              onChange={(e) => set({ name: e.target.value })}
            />
          )}
        </Field>
        <RadioGroup
          legend="Sex"
          name="sex"
          value={form.sex}
          error={errors.sex}
          options={(Object.keys(SEX_LABEL) as DogSex[]).map((v) => ({
            value: v,
            label: SEX_LABEL[v],
          }))}
          onChange={(v) => set({ sex: v })}
        />
        <Field
          label="Age estimate"
          help="For example: about 3 years"
          error={errors.age}
        >
          {({ id, describedBy, invalid }) => (
            <input
              id={id}
              type="text"
              value={form.age}
              aria-invalid={invalid}
              aria-describedby={describedBy}
              onChange={(e) => set({ age: e.target.value })}
            />
          )}
        </Field>
        <RadioGroup
          legend="Size"
          name="size"
          value={form.size}
          error={errors.size}
          options={(Object.keys(SIZE_LABEL) as DogSize[]).map((v) => ({
            value: v,
            label: SIZE_LABEL[v],
          }))}
          onChange={(v) => set({ size: v })}
        />
        <Field
          label="Location (optional)"
          help="Shown on the public profile."
          error={errors.location}
        >
          {({ id, describedBy, invalid }) => (
            <input
              id={id}
              type="text"
              value={form.location}
              aria-invalid={invalid}
              aria-describedby={describedBy}
              onChange={(e) => set({ location: e.target.value })}
            />
          )}
        </Field>
      </form>
      {discard ? (
        <ConfirmDialog
          title="Discard your changes?"
          confirmLabel="Discard"
          cancelLabel="Keep editing"
          danger
          onConfirm={() => navigate(backTo)}
          onCancel={() => setDiscard(false)}
        >
          <p>Your changes to this dog are not saved.</p>
        </ConfirmDialog>
      ) : null}
    </Screen>
  );
}
