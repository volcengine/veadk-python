import type { HTMLAttributes, ReactNode } from "react";
import { Button } from "../../primitives/Button";
import avatarBackground from "./assets/avatar-background.png";
import avatarLetter from "./assets/avatar-letter-d.svg";
import statusDot from "./assets/status-dot.svg";
import editIcon from "./assets/edit.svg";
import chatIcon from "./assets/chat.svg";
import "./Header.css";

export interface HeaderProps extends Omit<HTMLAttributes<HTMLElement>, "title"> {
  title: string;
  description: string;
  status?: string;
  avatar?: ReactNode;
  onEdit?: () => void;
  onChat?: () => void;
}

export function Header({
  title,
  description,
  status = "ACTIVE",
  avatar,
  onEdit,
  onChat,
  className = "",
  ...props
}: HeaderProps) {
  return (
    <header {...props} className={`studio-header ${className}`.trim()}>
      <div className="studio-header__identity">
        <div className="studio-header__avatar" aria-hidden="true">
          {avatar ?? <>
            <img className="studio-header__avatar-background" src={avatarBackground} alt="" />
            <span className="studio-header__avatar-shade" />
            <img className="studio-header__avatar-letter" src={avatarLetter} alt="" />
          </>}
        </div>
        <div className="studio-header__content">
          <div className="studio-header__heading">
            <h1 className="studio-header__title">{title}</h1>
            <span className="studio-header__status">
              <img src={statusDot} alt="" aria-hidden="true" />
              <span>{status}</span>
            </span>
          </div>
          <p className="studio-header__description" title={description}>{description}</p>
        </div>
      </div>
      <div className="studio-header__actions">
        <Button
          className="studio-header__edit"
          variant="secondary"
          startIcon={<img src={editIcon} alt="" />}
          onClick={onEdit}
        >Edit</Button>
        <Button
          className="studio-header__chat"
          startIcon={<img src={chatIcon} alt="" />}
          onClick={onChat}
        >Chat</Button>
      </div>
    </header>
  );
}
