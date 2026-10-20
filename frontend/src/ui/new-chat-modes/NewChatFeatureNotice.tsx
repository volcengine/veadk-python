import { StudioUpdateControl } from "../StudioUpdateControl";
import { parseReleaseNotes } from "../releaseNotes";
import { useTranslation } from "react-i18next";

const bundledReleaseNotes = parseReleaseNotes(
  import.meta.env.VITE_STUDIO_RELEASE_CHANGELOG,
);
export function NewChatFeatureNotice({ canUpdate = false }: { canUpdate?: boolean }) {
  const { t } = useTranslation("newChat");
  const releaseNotes = bundledReleaseNotes.length
    ? bundledReleaseNotes
    : [
        t("featureNotice.defaultNotes.multiRegion"),
        t("featureNotice.defaultNotes.switchAgent"),
        t("featureNotice.defaultNotes.visualCanvas"),
      ];
  return (
    <div className="welcome-feature-pill">
      <span>{t("featureNotice.badge")}</span>
      <span className="welcome-feature-divider" aria-hidden="true" />
      <button
        type="button"
        className="welcome-feature-link"
        aria-describedby="welcome-feature-popover"
      >
        {t("featureNotice.view")}
      </button>
      <section
        id="welcome-feature-popover"
        className="welcome-feature-popover"
        role="tooltip"
      >
        <strong>{t("featureNotice.title")}</strong>
        <ul>
          {releaseNotes.map((note) => (
            <li key={note}>{note}</li>
          ))}
        </ul>
      </section>
      {canUpdate && <StudioUpdateControl variant="feature-link" />}
    </div>
  );
}
