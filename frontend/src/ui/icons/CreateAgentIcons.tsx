import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;

function IconRoot({ children, ...props }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      aria-hidden="true"
      {...props}
    >
      {children}
    </svg>
  );
}

/** Figma `blocks` instance used by the template entry card. */
export function TemplateBlocksIcon(props: IconProps) {
  return (
    <IconRoot {...props}>
      <path
        d="M10 21V8C10 7.73478 9.89464 7.48043 9.70711 7.29289C9.51957 7.10536 9.26522 7 9 7H4C3.73478 7 3.48043 7.10536 3.29289 7.29289C3.10536 7.48043 3 7.73478 3 8V20C3 20.2652 3.10536 20.5196 3.29289 20.7071C3.48043 20.8946 3.73478 21 4 21H16C16.2652 21 16.5196 20.8946 16.7071 20.7071C16.8946 20.5196 17 20.2652 17 20V15C17 14.7348 16.8946 14.4804 16.7071 14.2929C16.5196 14.1054 16.2652 14 16 14H3M15 3H20C20.5523 3 21 3.44772 21 4V9C21 9.55228 20.5523 10 20 10H15C14.4477 10 14 9.55228 14 9V4C14 3.44772 14.4477 3 15 3Z"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </IconRoot>
  );
}

/** Figma `Code` instance used by the code-package entry card. */
export function CodePackageIcon(props: IconProps) {
  return (
    <IconRoot {...props}>
      <path
        d="M13.2675 2.83686C13.3575 2.43269 13.7588 2.17769 14.163 2.26752C14.5672 2.35751 14.8222 2.75878 14.7324 3.16303L10.7324 21.163C10.6424 21.5672 10.2411 21.8222 9.83686 21.7324C9.43269 21.6424 9.17769 21.2411 9.26752 20.8369L13.2675 2.83686ZM6.46967 6.46967C6.76256 6.17678 7.23732 6.17678 7.53022 6.46967C7.82311 6.76256 7.82311 7.23732 7.53022 7.53022L3.06049 11.9999L7.53022 16.4697C7.82311 16.7626 7.82311 17.2373 7.53022 17.5302C7.23732 17.8231 6.76256 17.8231 6.46967 17.5302L1.46967 12.5302C1.17678 12.2373 1.17678 11.7626 1.46967 11.4697L6.46967 6.46967ZM16.4697 6.46967C16.7626 6.17678 17.2373 6.17678 17.5302 6.46967L22.5302 11.4697C22.8231 11.7626 22.8231 12.2373 22.5302 12.5302L17.5302 17.5302C17.2373 17.8231 16.7626 17.8231 16.4697 17.5302C16.1768 17.2373 16.1768 16.7626 16.4697 16.4697L20.9394 11.9999L16.4697 7.53022C16.1768 7.23732 16.1768 6.76256 16.4697 6.46967Z"
        fill="currentColor"
      />
    </IconRoot>
  );
}

/** Figma `codepen` instance used by the existing-project migration card. */
export function ExistingMigrationIcon(props: IconProps) {
  return (
    <IconRoot {...props}>
      <path
        d="M12 9.00019L4.06386 14.1587C3.37601 14.6058 3.03209 14.8293 2.91297 15.1128C2.80888 15.3606 2.80888 15.6398 2.91297 15.8875M12 9.00019L19.9361 14.1587C20.624 14.6058 20.9679 14.8293 21.087 15.1128C21.1911 15.3606 21.1911 15.6398 21.087 15.8875M12 9.00019V2.50019M12 15.0002L4.06386 9.8417C3.37601 9.39459 3.03209 9.17104 2.91297 8.88755C2.80888 8.6398 2.80888 8.36057 2.91297 8.11282M12 15.0002L19.9361 9.8417C20.624 9.39459 20.9679 9.17104 21.087 8.88755C21.1911 8.6398 21.1911 8.36057 21.087 8.11282M12 15.0002V21.5002M21.272 15.9734L12.872 21.4334C12.5564 21.6386 12.3985 21.7411 12.2285 21.781C12.0782 21.8163 11.9218 21.8163 11.7715 21.781C11.6015 21.7411 11.4436 21.6386 11.128 21.4334L2.72802 15.9734C2.46201 15.8005 2.32901 15.714 2.23265 15.5987C2.14735 15.4966 2.08327 15.3786 2.04417 15.2514C2 15.1078 2 14.9491 2 14.6319V9.36848C2 9.05122 2 8.89259 2.04417 8.74895C2.08327 8.6218 2.14735 8.50372 2.23265 8.40165C2.32901 8.28633 2.46201 8.19988 2.72802 8.02697L11.128 2.56697C11.4436 2.36182 11.6015 2.25924 11.7715 2.21933C11.9218 2.18405 12.0782 2.18405 12.2285 2.21933C12.3985 2.25924 12.5564 2.36182 12.872 2.56697L21.272 8.02697C21.538 8.19988 21.671 8.28633 21.7674 8.40165C21.8527 8.50372 21.9167 8.6218 21.9558 8.74895C22 8.89259 22 9.05122 22 9.36848V14.6319C22 14.9491 22 15.1078 21.9558 15.2514C21.9167 15.3786 21.8527 15.4966 21.7674 15.5987C21.671 15.714 21.538 15.8005 21.272 15.9734Z"
        stroke="currentColor"
        strokeWidth="1.3"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </IconRoot>
  );
}

export function CreateBackIcon(props: IconProps) {
  return (
    <svg
      viewBox="0 0 15 15"
      fill="none"
      aria-hidden="true"
      {...props}
    >
      <path
        d="M1.80403 0.218866C1.51221 -0.0729552 1.03907 -0.0729552 0.747253 0.218865L0.218865 0.747254C-0.0729552 1.03907 -0.0729551 1.51221 0.218866 1.80403L4.44597 6.03113C4.59266 6.17783 4.78517 6.25078 4.97743 6.24999C5.16969 6.25078 5.3622 6.17783 5.50889 6.03113L9.73599 1.80403C10.0278 1.51221 10.0278 1.03907 9.73599 0.747254L9.20761 0.218865C8.91578 -0.0729552 8.44265 -0.0729552 8.15083 0.218866L4.97743 3.39227L1.80403 0.218866Z"
        fill="currentColor"
        transform="translate(10.625 2.52257) rotate(90)"
      />
    </svg>
  );
}

export function CreateSendIcon(props: IconProps) {
  return (
    <IconRoot {...props}>
      <path
        d="M12 17V7m0 0-4 4m4-4 4 4"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </IconRoot>
  );
}

export function CreateDebugIcon(props: IconProps) {
  return (
    <svg
      viewBox="0 0 10 10"
      fill="none"
      aria-hidden="true"
      {...props}
    >
      <path
        d="M2.083 2.07948C2.083 1.67483 2.083 1.47251 2.16737 1.36098C2.24087 1.26382 2.35322 1.20369 2.47483 1.19643C2.61443 1.1881 2.78278 1.30033 3.11947 1.52479L7.50095 4.44578C7.77915 4.63125 7.91825 4.72398 7.96673 4.84086C8.0091 4.94305 8.0091 5.0579 7.96673 5.16009C7.91825 5.27697 7.77915 5.36971 7.50095 5.55518L3.11947 8.47617C2.78278 8.70063 2.61443 8.81286 2.47483 8.80452C2.35322 8.79726 2.24087 8.73713 2.16737 8.63997C2.083 8.52844 2.083 8.32612 2.083 7.92147V2.07948Z"
        fill="currentColor"
      />
    </svg>
  );
}

export function CreateDeployIcon(props: IconProps) {
  return (
    <IconRoot {...props}>
      <path
        d="m9.25 7-5 5 5 5M14.75 7l5 5-5 5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </IconRoot>
  );
}

export function CreateDownloadIcon(props: IconProps) {
  return (
    <IconRoot {...props}>
      <path
        d="M12 3v11m0 0-4-4m4 4 4-4M5 19h14"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </IconRoot>
  );
}

export function CreateShareIcon(props: IconProps) {
  return (
    <IconRoot {...props}>
      <path
        d="M8.5 12.5 15.5 8m-7 3.5 7 4.5M18 5.5a2.5 2.5 0 1 1-5 0 2.5 2.5 0 0 1 5 0ZM8 12a2.5 2.5 0 1 1-5 0 2.5 2.5 0 0 1 5 0Zm10.5 5.5a2.5 2.5 0 1 1-5 0 2.5 2.5 0 0 1 5 0Z"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </IconRoot>
  );
}

export function CreateAddIcon(props: IconProps) {
  return (
    <svg
      viewBox="0 0 17.5 17.5"
      fill="none"
      aria-hidden="true"
      {...props}
    >
      <path
        d="M8 16.75V9.5H0.75C0.335786 9.5 0 9.16421 0 8.75C0 8.33579 0.335786 8 0.75 8H8V0.75C8 0.335786 8.33579 0 8.75 0C9.16421 0 9.5 0.335786 9.5 0.75V8H16.75C17.1642 8 17.5 8.33579 17.5 8.75C17.5 9.16421 17.1642 9.5 16.75 9.5H9.5V16.75C9.5 17.1642 9.16421 17.5 8.75 17.5C8.33579 17.5 8 17.1642 8 16.75Z"
        fill="currentColor"
      />
    </svg>
  );
}

export function CreateCloseIcon(props: IconProps) {
  return (
    <svg
      viewBox="0 0 16 16"
      fill="none"
      aria-hidden="true"
      {...props}
    >
      <path
        d="M9.47978 0.146447C9.67504 -0.0488153 9.99155 -0.0488155 10.1868 0.146447C10.3821 0.341709 10.3821 0.658216 10.1868 0.853478L5.87366 5.16663L10.1868 9.47978C10.3821 9.67504 10.3821 9.99155 10.1868 10.1868C9.99155 10.3821 9.67504 10.3821 9.47978 10.1868L5.16663 5.87366L0.853478 10.1868C0.658216 10.3821 0.341709 10.3821 0.146447 10.1868C-0.0488155 9.99155 -0.0488153 9.67504 0.146447 9.47978L4.4596 5.16663L0.146447 0.853478C-0.0488155 0.658216 -0.0488155 0.341709 0.146447 0.146447C0.341709 -0.0488155 0.658216 -0.0488155 0.853478 0.146447L5.16663 4.4596L9.47978 0.146447Z"
        fill="currentColor"
        transform="translate(2.83335 2.83335)"
      />
    </svg>
  );
}

/** Figma `settings-04` used by the debug workspace settings entry. */
export function DebugSettingsIcon(props: IconProps) {
  return (
    <svg
      viewBox="0 0 15 12"
      fill="none"
      aria-hidden="true"
      {...props}
    >
      <path
        d="M0.75 3H9.75M9.75 3A2.25 2.25 0 1 0 14.25 3A2.25 2.25 0 0 0 9.75 3ZM5.25 9H14.25M5.25 9A2.25 2.25 0 1 1 0.75 9A2.25 2.25 0 0 1 5.25 9Z"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** Figma `message-smile-square` used by the create conversation drawer. */
export function MessageSmileSquareIcon(props: IconProps) {
  return (
    <IconRoot {...props}>
      <path
        d="M7.25 3.5h9.5A3.75 3.75 0 0 1 20.5 7.25v7A3.75 3.75 0 0 1 16.75 18H12l-4.5 3.5V18h-.25a3.75 3.75 0 0 1-3.75-3.75v-7A3.75 3.75 0 0 1 7.25 3.5Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <path
        d="M8.5 13.5c1 1.2 2.17 1.8 3.5 1.8s2.5-.6 3.5-1.8"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <circle cx="9" cy="9.5" r="1.15" fill="currentColor" />
      <circle cx="15" cy="9.5" r="1.15" fill="currentColor" />
    </IconRoot>
  );
}

/** Figma `face-id-square` used by the selected Agent inspector. */
export function AgentFaceSquareIcon(props: IconProps) {
  return (
    <IconRoot {...props}>
      <g transform="translate(2 2)">
        <path
          d="M5.5 6V7.5M14.5 6V7.5M9 10.6001C9.8 10.6001 10.5 9.9001 10.5 9.1001V6M13.2002 13.2C11.4002 15 8.5002 15 6.7002 13.2M1 5.8V14.2C1 15.8802 1 16.7202 1.32698 17.362C1.6146 17.9265 2.07354 18.3854 2.63803 18.673C3.27976 19 4.11984 19 5.8 19H14.2C15.8802 19 16.7202 19 17.362 18.673C17.9265 18.3854 18.3854 17.9265 18.673 17.362C19 16.7202 19 15.8802 19 14.2V5.8C19 4.11984 19 3.27977 18.673 2.63803C18.3854 2.07354 17.9265 1.6146 17.362 1.32698C16.7202 1 15.8802 1 14.2 1H5.8C4.11984 1 3.27977 1 2.63803 1.32698C2.07354 1.6146 1.6146 2.07354 1.32698 2.63803C1 3.27976 1 4.11984 1 5.8Z"
          stroke="currentColor"
          strokeWidth="2"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </g>
    </IconRoot>
  );
}

/** Figma image mark used by the debug workspace empty state. */
export function DebugWorkspaceMarkIcon(props: IconProps) {
  return (
    <svg
      viewBox="0 0 44 43"
      fill="none"
      aria-hidden="true"
      {...props}
    >
      <path
        d="M4 13.25C4 8.14 8.14 4 13.25 4h13.5C31.86 4 36 8.14 36 13.25v6.5l-6 6V13H13v17h13l-6 6h-6.75C8.14 36 4 31.86 4 26.75v-13.5Z"
        fill="currentColor"
      />
      <path d="M29 27h11v11H29V27Z" fill="currentColor" />
      <path d="m29 27 11-11v11H29Z" fill="white" />
    </svg>
  );
}

/** Figma `message-circle-dashed` used by the canvas user-request terminal. */
export function TerminalUserRequestIcon(props: IconProps) {
  return (
    <svg
      viewBox="0 0 14 14"
      fill="none"
      aria-hidden="true"
      {...props}
    >
      <path
        d="M8.33335 0.733333C8.00002 0.733333 7.66668 0.666667 7.33335 0.666667C7.00002 0.666667 6.66668 0.733333 6.33335 0.733333M12.2 3.19997C11.8023 2.66903 11.3309 2.1976 10.8 1.79997M13.2666 7.66667C13.3333 7.33333 13.3333 7 13.3333 6.66667C13.3333 6.33333 13.2666 6 13.2666 5.66667M10.8 11.5333C11.3309 11.1357 11.8023 10.6642 12.2 10.1333M6.33335 12.5999C6.66668 12.6666 7.00002 12.6666 7.33335 12.6666C7.66668 12.6666 8.00002 12.5999 8.33335 12.5999M1.66668 10.3333L0.666685 13.3333L3.66668 12.3333M1.40002 5.66667C1.40002 6 1.33335 6.33333 1.33335 6.66667C1.33335 7 1.40002 7.33333 1.40002 7.66667M3.86665 1.79997C3.33572 2.1976 2.86429 2.66903 2.46665 3.19997"
        stroke="currentColor"
        strokeWidth="1.33333"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** Figma `bot-message-square` used by the canvas final-reply terminal. */
export function TerminalFinalReplyIcon(props: IconProps) {
  return (
    <svg
      viewBox="0 0 18.3333 18.3334"
      fill="none"
      aria-hidden="true"
      {...props}
    >
      <path
        d="M9.16667 4.16667V0.833333H5.83333M0.833333 9.16667H2.5M6.66667 8.33333V10M11.6667 8.33333V10M15.8333 9.16667H17.5M5.83333 14.1667L2.5 17.5V5.83333C2.5 5.39131 2.67559 4.96738 2.98816 4.65482C3.30072 4.34226 3.72464 4.16667 4.16667 4.16667H14.1667C14.6087 4.16667 15.0326 4.34226 15.3452 4.65482C15.6577 4.96738 15.8333 5.39131 15.8333 5.83333V12.5C15.8333 12.942 15.6577 13.366 15.3452 13.6785C15.0326 13.9911 14.6087 14.1667 14.1667 14.1667H5.83333Z"
        stroke="currentColor"
        strokeWidth="1.66667"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}
