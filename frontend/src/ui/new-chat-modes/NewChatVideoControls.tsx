import {
  useEffect,
  useId,
  useState,
  type ChangeEvent,
  type SVGProps,
} from "react";
import { motion, useReducedMotion } from "motion/react";
import { useTranslation } from "react-i18next";
import { NewChatCompactSelect } from "./NewChatCompactSelect";
import {
  VIDEO_ASPECT_RATIO_OPTIONS,
  VIDEO_RESOLUTION_OPTIONS,
  type NewChatVideoConfig,
  type VideoAspectRatio,
  type VideoResolution,
} from "./video-types";
import "./new-chat-video-controls.css";

export interface NewChatVideoControlsProps {
  config: NewChatVideoConfig;
  onChange: (config: NewChatVideoConfig) => void;
  disabled?: boolean;
  enhancerModel: string;
  assetStorageAvailable: boolean;
  assetStorageUnavailableReason?: string;
  modelsLoading?: boolean;
  modelsError?: string;
}

export interface NewChatInlineAssetInputProps {
  asset: File | null;
  onChange: (asset: File | null) => void;
  disabled?: boolean;
  unavailableReason?: string;
  kind: "image" | "video";
  label: string;
}

interface VideoAssetInputProps {
  label: string;
  helper: string;
  accept: string;
  asset: File | null;
  onChange: (asset: File | null) => void;
  disabled: boolean;
  kind: "image" | "video";
}

function AssetIcon({
  kind,
  ...props
}: SVGProps<SVGSVGElement> & { kind: "image" | "video" }) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.75"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      {...props}
    >
      {kind === "image" ? (
        <>
          <rect x="3.5" y="4" width="17" height="16" rx="2.5" />
          <circle cx="9" cy="9.25" r="1.5" />
          <path d="m5.75 17 4.1-4.1a1.25 1.25 0 0 1 1.77 0l1.35 1.35 1.55-1.55a1.25 1.25 0 0 1 1.77 0L19 15.4" />
        </>
      ) : (
        <>
          <rect x="3.5" y="5" width="12.5" height="14" rx="2.5" />
          <path d="m16 9.5 3.1-1.75a.9.9 0 0 1 1.35.78v6.94a.9.9 0 0 1-1.35.78L16 14.5" />
          <path d="m9 9.5 3.5 2.5L9 14.5Z" />
        </>
      )}
    </svg>
  );
}

function RemoveIcon(props: SVGProps<SVGSVGElement>) {
  return (
    <svg
      viewBox="0 0 16 16"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.5"
      strokeLinecap="round"
      aria-hidden="true"
      {...props}
    >
      <path d="m4.5 4.5 7 7m0-7-7 7" />
    </svg>
  );
}

export function NewChatInlineAssetInput({
  asset,
  onChange,
  disabled = false,
  unavailableReason = "",
  kind,
  label,
}: NewChatInlineAssetInputProps) {
  const { t } = useTranslation("newChat");
  const inputId = useId();
  const [previewUrl, setPreviewUrl] = useState("");

  useEffect(() => {
    if (!asset) {
      setPreviewUrl("");
      return;
    }
    const nextPreviewUrl = URL.createObjectURL(asset);
    setPreviewUrl(nextPreviewUrl);
    return () => URL.revokeObjectURL(nextPreviewUrl);
  }, [asset]);

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const nextAsset = event.currentTarget.files?.[0] ?? null;
    if (nextAsset) onChange(nextAsset);
    event.currentTarget.value = "";
  }

  return (
    <div
      className={`new-chat-inline-video${asset ? " has-preview" : ""}${disabled ? " is-disabled" : ""}`}
    >
      <input
        id={inputId}
        className="new-chat-inline-video__input"
        type="file"
        accept={`${kind}/*`}
        disabled={disabled}
        required
        aria-label={t("video.controls.upload", { label })}
        onChange={handleFileChange}
      />
      <label
        className="new-chat-inline-video__tile"
        htmlFor={inputId}
        title={
          unavailableReason ||
          (asset
            ? t("video.controls.replaceFile", { label, name: asset.name })
            : t("video.controls.upload", { label }))
        }
      >
        {previewUrl && kind === "image" ? (
          <img src={previewUrl} alt="" />
        ) : previewUrl ? (
          <video
            src={previewUrl}
            muted
            playsInline
            preload="metadata"
            aria-hidden="true"
          />
        ) : (
          <>
            <AssetIcon kind={kind} />
            <span>{label}</span>
          </>
        )}
      </label>
      {asset ? (
        <button
          className="new-chat-inline-video__remove"
          type="button"
          aria-label={t("video.controls.removeFile", { label, name: asset.name })}
          disabled={disabled}
          onClick={() => onChange(null)}
        >
          <RemoveIcon />
        </button>
      ) : null}
    </div>
  );
}

function ModelLoadingSpinner() {
  const { t } = useTranslation("newChat");
  return (
    <span
      className="new-chat-video-model-spinner"
      role="status"
      aria-label={t("video.controls.loadingEnhancer")}
    />
  );
}

function VideoAssetInput({
  label,
  helper,
  accept,
  asset,
  onChange,
  disabled,
  kind,
}: VideoAssetInputProps) {
  const { t } = useTranslation("newChat");
  const inputId = useId();

  function handleFileChange(event: ChangeEvent<HTMLInputElement>) {
    const nextAsset = event.currentTarget.files?.[0] ?? null;
    if (nextAsset) onChange(nextAsset);
    event.currentTarget.value = "";
  }

  return (
    <div className={`new-chat-video-asset${disabled ? " is-disabled" : ""}`}>
      <input
        id={inputId}
        className="new-chat-video-asset__input"
        type="file"
        accept={accept}
        disabled={disabled}
        onChange={handleFileChange}
      />
      <label className="new-chat-video-asset__label" htmlFor={inputId}>
        <span className="new-chat-video-asset__icon">
          <AssetIcon kind={kind} />
        </span>
        <span className="new-chat-video-asset__copy">
          <span className="new-chat-video-asset__title">
            {label}
            <small>{t("video.controls.optional")}</small>
          </span>
          <span
            className={`new-chat-video-asset__value${asset ? " is-selected" : ""}`}
            title={asset?.name}
          >
            {asset?.name || helper}
          </span>
        </span>
        <span className="new-chat-video-asset__action">
          {asset ? t("video.controls.replace") : t("video.controls.add")}
        </span>
      </label>
      {asset ? (
        <button
          className="new-chat-video-asset__remove"
          type="button"
          aria-label={t("video.controls.removeFile", { label, name: asset.name })}
          disabled={disabled}
          onClick={() => onChange(null)}
        >
          <RemoveIcon />
        </button>
      ) : null}
    </div>
  );
}

export function NewChatVideoControls({
  config,
  onChange,
  enhancerModel,
  assetStorageAvailable,
  assetStorageUnavailableReason = "",
  modelsLoading = false,
  modelsError = "",
  disabled = false,
}: NewChatVideoControlsProps) {
  const { t } = useTranslation("newChat");
  const reduceMotion = useReducedMotion();

  function update<K extends keyof NewChatVideoConfig>(
    key: K,
    value: NewChatVideoConfig[K],
  ) {
    onChange({ ...config, [key]: value });
  }

  const firstLastFrameMode = config.taskMode === "first_last_frame";
  const videoEditingMode = config.taskMode === "video_editing";
  const videoExtensionMode = config.taskMode === "video_extension";
  const assetInputsDisabled = disabled || !assetStorageAvailable;

  return (
    <motion.section
      className="new-chat-video-controls"
      aria-label={t("video.controls.label")}
      initial={reduceMotion ? false : { opacity: 0, y: -12, scaleY: 0.96 }}
      animate={{ opacity: 1, y: 0, scaleY: 1 }}
      exit={reduceMotion ? { opacity: 0 } : { opacity: 0, y: -8, scaleY: 0.98 }}
      transition={{
        duration: reduceMotion ? 0 : 0.2,
        ease: [0.22, 1, 0.36, 1],
      }}
    >
      <div className="new-chat-video-controls__parameters">
        <div className="new-chat-video-controls__field">
          <NewChatCompactSelect
            label={t("video.controls.aspectRatio")}
            value={config.aspectRatio}
            options={VIDEO_ASPECT_RATIO_OPTIONS}
            placeholder={t("video.controls.selectAspectRatio")}
            disabled={disabled}
            onChange={(value) =>
              update("aspectRatio", value as VideoAspectRatio)
            }
          />
        </div>

        <div className="new-chat-video-controls__field">
          <NewChatCompactSelect
            label={t("video.controls.resolution")}
            value={config.resolution}
            options={VIDEO_RESOLUTION_OPTIONS}
            placeholder={t("video.controls.selectResolution")}
            disabled={disabled}
            onChange={(value) => update("resolution", value as VideoResolution)}
          />
        </div>

        <label
          className={`new-chat-video-duration${disabled ? " is-disabled" : ""}`}
        >
          <span className="new-chat-video-duration__header">
            <span>{t("video.controls.duration")}</span>
            <output>{t("video.controls.durationShort", { count: config.durationSeconds })}</output>
          </span>
          <input
            type="range"
            min="4"
            max="30"
            step="1"
            value={config.durationSeconds}
            disabled={disabled}
            aria-label={t("video.controls.durationAria", { count: config.durationSeconds })}
            onChange={(event) =>
              update("durationSeconds", Number(event.currentTarget.value))
            }
          />
        </label>
      </div>

      <div
        className={`new-chat-video-controls__assets${firstLastFrameMode || videoEditingMode || videoExtensionMode ? " is-single" : ""}`}
      >
        {firstLastFrameMode ? (
          <VideoAssetInput
            label={t("video.controls.lastFrame")}
            helper={t("video.controls.lastFrameHelper")}
            accept="image/*"
            asset={config.lastFrame}
            disabled={assetInputsDisabled}
            kind="image"
            onChange={(asset) => update("lastFrame", asset)}
          />
        ) : (
          <>
            <VideoAssetInput
              label={
                videoEditingMode || videoExtensionMode
                  ? t("video.controls.assistImage")
                  : t("video.controls.referenceImage")
              }
              helper={
                videoEditingMode || videoExtensionMode
                  ? t("video.controls.assistImageHelper")
                  : t("video.controls.imageHelper")
              }
              accept="image/*"
              asset={config.referenceImage}
              disabled={assetInputsDisabled}
              kind="image"
              onChange={(asset) => update("referenceImage", asset)}
            />
            {videoEditingMode || videoExtensionMode ? null : (
              <VideoAssetInput
                label={t("video.controls.referenceVideo")}
                helper={t("video.controls.videoHelper")}
                accept="video/*"
                asset={config.referenceVideo}
                disabled={assetInputsDisabled}
                kind="video"
                onChange={(asset) => update("referenceVideo", asset)}
              />
            )}
          </>
        )}
      </div>
      {!assetStorageAvailable && assetStorageUnavailableReason ? (
        <p className="new-chat-video-controls__storage-unavailable" role="status">
          {assetStorageUnavailableReason}
        </p>
      ) : null}
      <p
        className="new-chat-video-controls__model-hint"
        title={modelsError || undefined}
      >
        {modelsLoading ? (
          <ModelLoadingSpinner />
        ) : enhancerModel ? (
          <>{t("video.controls.enhancerHint", { model: enhancerModel })}</>
        ) : (
          t("video.controls.enhancerUnavailable")
        )}
      </p>
    </motion.section>
  );
}
