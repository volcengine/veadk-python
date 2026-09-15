import { useState } from "react";
import { SidebarAgentIcon, type SidebarHistoryItem, type SidebarProps } from "../../components/composites/Sidebar";
import { useToast } from "../../components/primitives/Toast";
import { DeleteIcon } from "../../components/icons";
import newTask from "../../components/layouts/DetailPageLayout/assets/new-task.svg";
import resources from "../../components/layouts/DetailPageLayout/assets/resources.svg";
import files from "../../components/layouts/DetailPageLayout/assets/files.svg";
import profile from "../../components/layouts/DetailPageLayout/assets/profile.png";
import byteplusLogo from "../../assets/byteplus.svg";
import { ReviewIcon } from "../../ui/icons/ReviewIcon";
import { UsersIcon } from "../../users/UsersIcon";

const sessionTitles = [
  "Optimize page layout", "Build a customer support agent", "Improve resource search and model selection across the workspace",
  "Add Runtime info", "Review agent configuration", "Knowledge base search", "Prepare product release notes", "Analyze feedback",
  "Workspace setup", "Plan a research workflow",
];
const initialSessions = sessionTitles.map((label, index) => ({ id: `session-${index}`, label }));

/** Sidebar 展示区与 AppLayout 使用同一份示例数据和交互 */
export function useSidebarPreviewState() {
  const [provider, setProvider] = useState("volcengine");
  const [state, setState] = useState("ready");
  const [language, setLanguage] = useState("en");
  const [page, setPage] = useState("home");
  const [activeSession, setActiveSession] = useState<string>();
  const [sessions, setSessions] = useState(initialSessions);
  const [notifications, setNotifications] = useState(false);
  const toast = useToast();
  const showNotice = (title: string) => toast.add({ title });
  const icon = (src: string) => <img src={src} alt="" />;
  const navigation = [
    { id: "home", label: "New task", icon: icon(newTask) },
    { id: "search", label: "Search", icon: undefined },
    { id: "agents", label: "Agents", icon: <SidebarAgentIcon /> },
    { id: "resources", label: "Resources", icon: icon(resources) },
    { id: "files", label: "My files", icon: icon(files) },
  ].map(item => ({ ...item, selected: !activeSession && page === item.id, onSelect: () => { setPage(item.id); setActiveSession(undefined); } }));
  const adminItems = [
    { id: "review", label: "Review Center", icon: <ReviewIcon /> },
    { id: "users", label: "Users", icon: <UsersIcon /> },
  ].map(item => ({ ...item, selected: !activeSession && page === item.id, onSelect: () => { setPage(item.id); setActiveSession(undefined); } }));
  const historyItems: SidebarHistoryItem[] = sessions.map(session => ({
    ...session,
    selected: activeSession === session.id,
    loading: session.id === "session-1",
    onSelect: () => setActiveSession(session.id),
    menuItems: [{ id: "delete", label: "删除会话", icon: <DeleteIcon />, destructive: true, onSelect: () => {
      setSessions(items => items.filter(item => item.id !== session.id));
      if (activeSession === session.id) setActiveSession(undefined);
      showNotice("已删除示例会话");
    } }],
  }));
  const sidebar: Omit<SidebarProps, "collapsed" | "onCollapsedChange"> = {
    brand: { name: provider === "volcengine" ? "AK Studio" : "BytePlus Studio", logo: provider === "byteplus" ? icon(byteplusLogo) : undefined },
    navigation,
    navigationGroups: [{ id: "admin", label: "Admin", items: adminItems }],
    history: [{ id: "recent", label: "Recent", items: state === "ready" ? historyItems : [] }],
    loading: state === "loading",
    error: state === "error" ? "请稍后重试" : undefined,
    onRetry: () => setState("ready"),
    account: {
      name: "Chloe", avatarSrc: profile, avatarFit: "figma", email: "chloe@example.com", role: "Administrator",
      notification: { label: "通知", onClick: () => setNotifications(true) },
      update: { label: "Update", onClick: () => showNotice("当前已是最新版本") },
      menuItems: [
        { id: "system", label: "系统信息", onSelect: () => showNotice(provider === "volcengine" ? "AK Studio · 火山引擎" : "AK Studio · BytePlus") },
        { id: "language", label: "语言", children: [{ type: "radio-group", id: "language-options", value: language, onValueChange: setLanguage, items: [{ id: "en", label: "English" }, { id: "zh", label: "简体中文" }] }] },
        { id: "feedback", label: "反馈", onSelect: () => showNotice("已选择反馈") },
        { type: "separator", id: "account-separator" },
        { id: "logout", label: "退出登录", destructive: true, onSelect: () => showNotice("已选择退出登录") },
      ],
    },
  };
  const heading = activeSession ? sessions.find(item => item.id === activeSession)?.label : page === "home" ? undefined : [...navigation, ...adminItems].find(item => item.id === page)?.label;
  const reset = () => { setSessions(initialSessions); setState("ready"); setActiveSession(undefined); setPage("home"); };

  return { sidebar, heading, provider, setProvider, state, setState, reset, notifications, setNotifications };
}
