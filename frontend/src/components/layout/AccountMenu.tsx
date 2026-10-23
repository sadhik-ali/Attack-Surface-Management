import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import {
  ChevronDown,
  KeyRound,
  LogOut,
  Settings,
  ShieldCheck,
} from "lucide-react";

import { useAuth } from "@/context/AuthProvider";
import { apiRequest, errorMessage } from "@/lib/api";
import { useClickOutside } from "@/hooks/useClickOutside";
import { titleize } from "@/lib/labels";
import {
  Button,
  Input,
  Modal,
  Spinner,
  useToast,
} from "@/components/ui";

export function AccountMenu() {
  const { user, selectedCompany, logout } = useAuth();
  const [open, setOpen] = useState(false);
  const [passwordOpen, setPasswordOpen] = useState(false);
  const [signingOut, setSigningOut] = useState(false);
  const navigate = useNavigate();
  const ref = useClickOutside<HTMLDivElement>(() => setOpen(false), open);

  if (!user) return null;

  const initials = user.full_name
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");

  const onSignOut = async () => {
    setSigningOut(true);
    await logout();
    navigate("/login", { replace: true });
  };

  return (
    <div ref={ref} className="relative">
      <Button
        variant="ghost"
        size="sm"
        onClick={() => setOpen((current) => !current)}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-label="Account menu"
        className="gap-2 pl-1.5"
      >
        <span
          aria-hidden="true"
          className="flex h-6 w-6 items-center justify-center rounded-full text-[10px] font-semibold text-white"
          style={{ backgroundColor: user.avatar_color ?? "#3B82F6" }}
        >
          {initials || "U"}
        </span>
        <span className="hidden max-w-[8rem] truncate text-xs lg:inline">
          {user.full_name}
        </span>
        <ChevronDown aria-hidden="true" className="hidden h-3 w-3 lg:block" />
      </Button>

      {open ? (
        <div
          role="menu"
          className="absolute right-0 top-full z-50 mt-2 w-64 overflow-hidden rounded-card border border-border bg-surface-raised shadow-overlay"
        >
          <div className="border-b border-border px-3 py-2.5">
            <p className="truncate text-sm font-medium text-slate-100">
              {user.full_name}
            </p>
            <p className="truncate text-xs text-slate-500">{user.email}</p>
            <p className="mt-1.5 inline-flex items-center gap-1 rounded-full border border-brand-500/25 bg-brand-500/10 px-1.5 py-0.5 text-[10px] font-medium text-brand-400">
              <ShieldCheck aria-hidden="true" className="h-3 w-3" />
              {selectedCompany
                ? titleize(selectedCompany.role_code)
                : titleize(user.role_code)}
            </p>
          </div>

          <div className="p-1.5">
            <Link
              to="/settings"
              role="menuitem"
              onClick={() => setOpen(false)}
              className="flex items-center gap-2 rounded-md px-2.5 py-2 text-xs text-slate-300 transition-colors hover:bg-surface hover:text-slate-100"
            >
              <Settings aria-hidden="true" className="h-3.5 w-3.5" />
              Settings
            </Link>
            <button
              type="button"
              role="menuitem"
              onClick={() => {
                setOpen(false);
                setPasswordOpen(true);
              }}
              className="flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-left text-xs text-slate-300 transition-colors hover:bg-surface hover:text-slate-100"
            >
              <KeyRound aria-hidden="true" className="h-3.5 w-3.5" />
              Change password
            </button>
            <button
              type="button"
              role="menuitem"
              onClick={onSignOut}
              disabled={signingOut}
              className="flex w-full items-center gap-2 rounded-md px-2.5 py-2 text-left text-xs text-critical transition-colors hover:bg-critical/10 disabled:opacity-50"
            >
              {signingOut ? (
                <Spinner className="h-3.5 w-3.5" />
              ) : (
                <LogOut aria-hidden="true" className="h-3.5 w-3.5" />
              )}
              Sign out
            </button>
          </div>
        </div>
      ) : null}

      <ChangePasswordModal
        open={passwordOpen}
        onClose={() => setPasswordOpen(false)}
      />
    </div>
  );
}

function ChangePasswordModal({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const { toast } = useToast();
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const reset = () => {
    setCurrentPassword("");
    setNewPassword("");
    setConfirmPassword("");
    setError(null);
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setError(null);
    if (
      newPassword.length < 12 ||
      !/[A-Z]/.test(newPassword) ||
      !/[a-z]/.test(newPassword) ||
      !/\d/.test(newPassword)
    ) {
      setError(
        "Use at least 12 characters with an uppercase letter, a lowercase letter and a digit.",
      );
      return;
    }
    if (newPassword !== confirmPassword) {
      setError("The new passwords do not match.");
      return;
    }
    setSaving(true);
    try {
      const response = await apiRequest<{ message: string }>(
        "/auth/change-password",
        {
          method: "POST",
          body: {
            current_password: currentPassword,
            new_password: newPassword,
          },
        },
      );
      toast({
        title: "Password updated",
        description: response.message,
        variant: "success",
      });
      reset();
      onClose();
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      open={open}
      onClose={() => {
        reset();
        onClose();
      }}
      title="Change password"
      description="Minimum 12 characters, including upper and lower case letters and a digit."
      size="sm"
      footer={
        <>
          <Button
            variant="ghost"
            onClick={() => {
              reset();
              onClose();
            }}
            disabled={saving}
          >
            Cancel
          </Button>
          <Button type="submit" form="change-password-form" loading={saving}>
            Update password
          </Button>
        </>
      }
    >
      <form
        id="change-password-form"
        onSubmit={submit}
        className="flex flex-col gap-3"
      >
        <Input
          type="password"
          label="Current password"
          autoComplete="current-password"
          value={currentPassword}
          onChange={(event) => setCurrentPassword(event.target.value)}
          required
        />
        <Input
          type="password"
          label="New password"
          autoComplete="new-password"
          value={newPassword}
          onChange={(event) => setNewPassword(event.target.value)}
          hint="At least 12 characters with upper, lower and a number"
          required
        />
        <Input
          type="password"
          label="Confirm new password"
          autoComplete="new-password"
          value={confirmPassword}
          onChange={(event) => setConfirmPassword(event.target.value)}
          required
        />
        {error ? (
          <p role="alert" className="text-xs text-critical">
            {error}
          </p>
        ) : null}
      </form>
    </Modal>
  );
}
