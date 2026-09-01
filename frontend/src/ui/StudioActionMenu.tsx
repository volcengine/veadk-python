import { Button } from "@openai/apps-sdk-ui/components/Button";
import { DotsHorizontal } from "@openai/apps-sdk-ui/components/Icon";
import { Menu } from "@openai/apps-sdk-ui/components/Menu";

export interface StudioActionMenuItem {
  label: string;
  onSelect: () => void;
  disabled?: boolean;
  danger?: boolean;
  title?: string;
}

interface StudioActionMenuProps {
  label: string;
  menuLabel: string;
  items: readonly StudioActionMenuItem[];
  placement?: "top-end" | "bottom-end";
}

export function StudioActionMenu({
  label,
  menuLabel,
  items,
  placement = "bottom-end",
}: StudioActionMenuProps) {
  return (
    <Menu>
      <Menu.Trigger>
        <Button
          type="button"
          color="secondary"
          variant="ghost"
          size="md"
          iconSize="sm"
          uniform
          aria-label={label}
          title={label}
          disabled={items.length === 0}
        >
          <DotsHorizontal aria-hidden="true" />
        </Button>
      </Menu.Trigger>
      <Menu.Content
        side={placement === "top-end" ? "top" : "bottom"}
        align="end"
        minWidth={148}
      >
        <span className="sr-only">{menuLabel}</span>
        {items.map((item) => (
          <Menu.Item
            key={item.label}
            disabled={item.disabled}
            onSelect={item.onSelect}
          >
            <span title={item.title}>{item.label}</span>
          </Menu.Item>
        ))}
      </Menu.Content>
    </Menu>
  );
}
