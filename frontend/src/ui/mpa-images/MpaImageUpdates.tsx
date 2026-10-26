import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Button,
  FormLabel,
  InputWithTailIcon,
  Select,
} from "../../components/primitives";
import { ModalButton } from "../../components/composites/ModalButton";
import { requestMpaImage } from "../../adk/client";
import {
  ImageApiError,
  imageDetail,
  imageVersions,
  latestImagePreview,
  type LatestImagePreview,
  validImageReference,
  type ImageUpdateSource,
  type ImageComponent,
  type ImageDetail,
  type ImageVersions,
} from "../../adk/mpaImages";
import { TextShimmer } from "../text-shimmer/TextShimmer";
import "./MpaImageUpdates.css";

type Props = { runtimeId: string; region: string };
function reasonKey(error: unknown, fallback: string) {
  const reason = error instanceof ImageApiError ? error.reason : "";
  return [
    "forbidden",
    "stale",
    "busy",
    "ownership",
    "missing_worker",
    "rejected",
    "unchanged",
    "catalog_failed",
    "read_failed",
    "invalid_image",
    "latest_resolution_failed",
  ].includes(reason)
    ? reason
    : fallback;
}
function ImageCard({
  runtimeId,
  region,
  component,
}: Props & { component: ImageComponent }) {
  const { t } = useTranslation("mpaImages");
  const id = useId();
  const [detail, setDetail] = useState<ImageDetail | null>(null);
  const [catalog, setCatalog] = useState<ImageVersions | null>(null);
  const [detailError, setDetailError] = useState("");
  const [catalogError, setCatalogError] = useState("");
  const [actionError, setActionError] = useState("");
  const [reading, setReading] = useState(false);
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [tag, setTag] = useState("");
  const [manualImage, setManualImage] = useState("");
  const [manualTouched, setManualTouched] = useState(false);
  const [open, setOpen] = useState(false);
  const [preview, setPreview] = useState<LatestImagePreview | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState("");
  const reads = useRef<{
    detail?: AbortController;
    catalog?: AbortController;
    preview?: AbortController;
  }>({});
  const write = useRef<AbortController | null>(null);
  const actionMessage = useRef<HTMLParagraphElement>(null);

  function invalidatePreview() {
    reads.current.preview?.abort();
    reads.current.preview = undefined;
    setPreview(null);
    setPreviewLoading(false);
    setPreviewError("");
  }
  async function refreshDetail() {
    invalidatePreview();
    setOpen(false);
    reads.current.detail?.abort();
    const controller = new AbortController();
    reads.current.detail = controller;
    setReading(true);
    setDetailError("");
    try {
      const value = await requestMpaImage(runtimeId, region, component, "", {
        signal: controller.signal,
      }).then(imageDetail);
      if (!controller.signal.aborted) {
        if (value.component !== component)
          throw new ImageApiError("invalid_response");
        setDetail(value);
        setTag("");
        setUncertain(false);
        setActionError("");
      }
    } catch (error) {
      if (!controller.signal.aborted)
        setDetailError(reasonKey(error, "read_failed"));
    } finally {
      if (!controller.signal.aborted) setReading(false);
    }
  }
  async function refreshVersions(cursor = "") {
    invalidatePreview();
    setOpen(false);
    reads.current.catalog?.abort();
    const controller = new AbortController();
    reads.current.catalog = controller;
    setLoading(true);
    setCatalogError("");
    if (!cursor) {
      setTag("");
    }
    try {
      const value = await requestMpaImage(
        runtimeId,
        region,
        component,
        `/versions${cursor ? `?cursor=${encodeURIComponent(cursor)}` : ""}`,
        { signal: controller.signal },
      ).then(imageVersions);
      if (!controller.signal.aborted)
        setCatalog((previous) => ({
          ...value,
          tags: [
            ...new Set([
              ...(cursor ? (previous?.tags ?? []) : []),
              ...value.tags,
            ]),
          ],
        }));
    } catch (error) {
      if (!controller.signal.aborted)
        setCatalogError(reasonKey(error, "catalog_failed"));
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }
  useEffect(() => {
    void refreshDetail();
    void refreshVersions();
    return () => {
      reads.current.detail?.abort();
      reads.current.catalog?.abort();
      reads.current.preview?.abort();
      write.current?.abort();
    };
    // Parent keys each component by Runtime and region, preventing cross-Agent state reuse.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    if (actionError) actionMessage.current?.focus();
  }, [actionError]);
  const manualTarget = manualImage.trim();
  const manualValid = validImageReference(manualTarget);
  const manualInvalid = Boolean(manualTarget) && !manualValid;
  const target =
    manualTarget || (catalog && tag ? `${catalog.repository}:${tag}` : "");
  const publicLatest = !manualTarget && tag === "latest";
  const source: ImageUpdateSource = manualTarget
    ? { image: manualTarget }
    : {
        tag,
        ...(publicLatest && preview
          ? { selection: { image: preview.image, digest: preview.digest } }
          : {}),
      };
  const blocked =
    sending ||
    reading ||
    uncertain ||
    !detail?.canUpdate ||
    Boolean(detailError) ||
    !target ||
    (!publicLatest && target === detail.currentImage) ||
    (manualTarget
      ? !manualValid
      : loading ||
        Boolean(catalogError) ||
        !tag ||
        catalog?.repository !== detail.repository);
  const unchangedPreview =
    publicLatest && preview?.image === detail?.currentImage;
  const confirmBlocked =
    blocked ||
    (publicLatest &&
      (!preview ||
        previewLoading ||
        Boolean(previewError) ||
        unchangedPreview));
  async function loadPreview() {
    invalidatePreview();
    if (!detail || !publicLatest) return;
    const controller = new AbortController();
    reads.current.preview = controller;
    setPreviewLoading(true);
    try {
      const value = await requestMpaImage(
        runtimeId,
        region,
        component,
        `/latest-preview?revision=${encodeURIComponent(detail.revision)}`,
        { signal: controller.signal },
      ).then(latestImagePreview);
      if (!controller.signal.aborted) {
        if (
          value.component !== component ||
          value.revision !== detail.revision ||
          value.requestedImage !== target
        )
          throw new ImageApiError("invalid_response");
        setPreview(value);
      }
    } catch (error) {
      if (!controller.signal.aborted)
        setPreviewError(reasonKey(error, "latest_resolution_failed"));
    } finally {
      if (!controller.signal.aborted) setPreviewLoading(false);
    }
  }
  function openDialog() {
    setOpen(true);
    if (publicLatest) void loadPreview();
  }
  function close() {
    invalidatePreview();
    if (write.current) {
      write.current.abort();
      write.current = null;
      setSending(false);
      setUncertain(true);
      setActionError("outcome_unknown");
    }
    setOpen(false);
  }
  async function submit() {
    if (confirmBlocked || write.current || !detail || !open) return;
    const controller = new AbortController();
    write.current = controller;
    reads.current.detail?.abort();
    setSending(true);
    setActionError("");
    try {
      const value = await requestMpaImage(runtimeId, region, component, "", {
        method: "POST",
        body: JSON.stringify({ ...source, revision: detail.revision }),
        signal: controller.signal,
      }).then(imageDetail);
      if (!controller.signal.aborted) {
        setDetail(value);
        setOpen(false);
        setTag("");
        setManualImage("");
        setManualTouched(false);
      }
    } catch (error) {
      if (!controller.signal.aborted) {
        const unknown =
          !(error instanceof ImageApiError) ||
          (error.status >= 500 &&
            ![
              "catalog_failed",
              "read_failed",
              "latest_resolution_failed",
            ].includes(error.reason));
        setUncertain(unknown);
        setActionError(
          unknown ? "outcome_unknown" : reasonKey(error, "rejected"),
        );
        if (!unknown)
          setDetail((previous) =>
            previous ? { ...previous, canUpdate: false } : previous,
          );
      }
    } finally {
      if (!controller.signal.aborted) {
        write.current = null;
        setSending(false);
      }
    }
  }
  const tags = catalog?.tags ?? [];
  const phase = detail?.operation?.phase;
  return (
    <section
      className="mpa-image-card"
      data-component={component}
      aria-labelledby={`${id}-heading`}
    >
      <div className="mpa-image-header">
        <h4 id={`${id}-heading`}>{t(component)}</h4>
        <Button
          variant="ghost"
          size="compact"
          disabled={sending || reading}
          onClick={() => void refreshDetail()}
        >
          {t("refreshStatus")}
        </Button>
      </div>
      {reading && <TextShimmer>{t("loadingStatus")}</TextShimmer>}
      {detailError && <p role="alert">{t(`errors.${detailError}`)}</p>}
      {detail && (
        <dl className="mpa-image-metadata">
          <div>
            <dt>{t("currentImage")}</dt>
            <dd>{detail.currentImage || t("notAvailable")}</dd>
          </div>
          <div>
            <dt>{t("cloudStatus")}</dt>
            <dd>{detail.status || t("notAvailable")}</dd>
          </div>
        </dl>
      )}
      {detail?.reason && (
        <p className="mpa-image-help">
          {t(`errors.${detail.reason}`, { defaultValue: t("errors.busy") })}
        </p>
      )}
      {phase && (
        <div className="mpa-image-operation" role="status">
          <p>{t(`phases.${phase}`)}</p>
          <p className="mpa-image-address">{detail?.operation?.target}</p>
        </div>
      )}
      <p className="mpa-image-help">
        {t(component === "worker" ? "workerHelp" : "runtimeHelp")}
      </p>
      <p id={`${id}-source-help`} className="mpa-image-help">
        {t("sourceHelp")}
      </p>
      <div className="mpa-image-field">
        <FormLabel htmlFor={`${id}-manual`}>{t("manualImage")}</FormLabel>
        <InputWithTailIcon
          id={`${id}-manual`}
          className="mpa-image-input"
          placeholder={t("imagePlaceholder")}
          type="text"
          autoComplete="off"
          spellCheck={false}
          value={manualImage}
          maxLength={2048}
          tailIcon={null}
          disabled={sending}
          aria-invalid={(manualTouched && manualInvalid) || undefined}
          aria-describedby={`${id}-source-help${manualTouched && manualInvalid ? ` ${id}-image-error` : ""}`}
          onBlur={() => setManualTouched(true)}
          onChange={(event) => {
            invalidatePreview();
            setOpen(false);
            setManualImage(event.target.value);
            setTag("");
          }}
        />
        {manualTouched && manualInvalid && (
          <p id={`${id}-image-error`} role="alert">
            {t("errors.invalid_image")}
          </p>
        )}
      </div>
      <div className="mpa-image-field">
        <FormLabel htmlFor={`${id}-version`}>{t("version")}</FormLabel>
        <Select
          id={`${id}-version`}
          value={tag}
          disabled={
            sending || loading || !catalog?.tags.length || Boolean(catalogError)
          }
          options={[
            { value: "", label: t("selectVersion"), disabled: true },
            ...[...new Set([...(tag ? [tag] : []), ...tags])].map((value) => ({
              value,
              label: value,
            })),
          ]}
          onChange={(event) => {
            invalidatePreview();
            setOpen(false);
            setTag(event.target.value);
            setManualImage("");
            setManualTouched(false);
          }}
        />
      </div>
      {loading && <TextShimmer>{t("loadingVersions")}</TextShimmer>}
      {!loading && catalog && !catalogError && !tags.length && (
        <p className="mpa-image-help">{t("empty")}</p>
      )}
      {catalogError && <p role="alert">{t(`errors.${catalogError}`)}</p>}
      <p className="mpa-image-address">
        {manualInvalid ? "" : target || catalog?.repository}
      </p>
      <div className="mpa-image-actions">
        <Button
          variant="outline"
          size="compact"
          disabled={sending || loading}
          onClick={() => void refreshVersions()}
        >
          {t("refreshVersions")}
        </Button>
        {catalog?.nextCursor && (
          <Button
            variant="ghost"
            size="compact"
            disabled={sending || loading}
            onClick={() => void refreshVersions(catalog.nextCursor)}
          >
            {t("loadMore")}
          </Button>
        )}
        <ModalButton
          label={t("update")}
          title={t("confirmation", { component: t(component) })}
          topGlow={false}
          open={open}
          onOpenChange={(value) => (value ? openDialog() : close())}
          onClose={close}
          closeLabel={t("close")}
          buttonProps={{ size: "compact", disabled: blocked }}
          footer={
            <>
              <Button variant="outline" onClick={close}>
                {t(sending ? "close" : "cancel")}
              </Button>
              <Button disabled={confirmBlocked} onClick={() => void submit()}>
                {t(sending ? "submitting" : "confirm")}
              </Button>
            </>
          }
        >
          <div className="mpa-image-confirm">
            <p>{t("confirmHelp", { component: t(component) })}</p>
            <div>
              <FormLabel>{t("currentImage")}</FormLabel>
              <p className="mpa-image-address">{detail?.currentImage}</p>
            </div>
            <div>
              <FormLabel>{t("targetImage")}</FormLabel>
              <p className="mpa-image-address">
                {publicLatest ? preview?.image || t("notAvailable") : target}
              </p>
            </div>
            <p className="mpa-image-help">
              {t(component === "worker" ? "workerHelp" : "runtimeHelp")}
            </p>
            {publicLatest && (
              <>
                <div>
                  <FormLabel>{t("requestedImage")}</FormLabel>
                  <p className="mpa-image-address">{target}</p>
                </div>
                {preview && (
                  <div>
                    <FormLabel>{t("digest")}</FormLabel>
                    <p className="mpa-image-address">{preview.digest}</p>
                  </div>
                )}
                {previewLoading && (
                  <div role="status">
                    <TextShimmer>{t("resolvingLatest")}</TextShimmer>
                  </div>
                )}
                {previewError && (
                  <div>
                    <p role="alert">{t(`errors.${previewError}`)}</p>
                    <Button
                      variant="outline"
                      onClick={() => void loadPreview()}
                    >
                      {t("retryResolution")}
                    </Button>
                  </div>
                )}
                {unchangedPreview && (
                  <p role="status">{t("errors.unchanged")}</p>
                )}
              </>
            )}
            {sending && <TextShimmer>{t("submitting")}</TextShimmer>}
            {actionError && (
              <p role="alert" ref={actionMessage} tabIndex={-1}>
                {t(`errors.${actionError}`)}
              </p>
            )}
          </div>
        </ModalButton>
      </div>
      {actionError && !open && <p role="alert">{t(`errors.${actionError}`)}</p>}
    </section>
  );
}
export function MpaImageUpdates(props: Props) {
  return (
    <div className="mpa-images">
      {(["runtime", "worker"] as const).map((component) => (
        <ImageCard
          key={`${props.region}:${props.runtimeId}:${component}`}
          {...props}
          component={component}
        />
      ))}
    </div>
  );
}
