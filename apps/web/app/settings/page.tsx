import { SettingsPanel } from "@/components/settings-panel";


export default function SettingsPage() {
  return (
    <div className="stack">
      <section>
        <div className="brand-kicker">Configuration checks</div>
        <div className="page-title">Settings</div>
      </section>
      <SettingsPanel />
    </div>
  );
}

