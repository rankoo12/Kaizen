import { Route, Routes } from "react-router-dom";
import { LandingPage } from "./pages/LandingPage";
import { DashboardPage } from "./pages/DashboardPage";
import { SettingsPage } from "./pages/SettingsPage";
import { ShortcutsPage } from "./pages/ShortcutsPage";
import { AboutPage } from "./pages/AboutPage";
import { TestsPage } from "./pages/TestsPage";
import { RunsPage } from "./pages/RunsPage";
import { InsightsPage } from "./pages/InsightsPage";
import { ModelsSettingsPage } from "./pages/ModelsSettingsPage";
import { ArtifactsPage } from "./pages/ArtifactsPage";
import { RunDetailsPage } from "./pages/RunDetailsPage";
import { SnapshotUploadPage } from "./pages/SnapshotUploadPage";
import { TestEditorPage } from "./pages/TestEditorPage";
import { CreateSuitePage } from "./pages/CreateSuitePage";
import { AppShell } from "./layouts/AppShell";

export const App = () => {
  return (
    <Routes>
      <Route path="/" element={<LandingPage />} />
      <Route element={<AppShell />}>
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/tests" element={<TestsPage />} />
        <Route path="/tests/new" element={<TestEditorPage />} />
        <Route path="/tests/:testId/edit" element={<TestEditorPage />} />
        <Route path="/suites/new" element={<CreateSuitePage />} />
        <Route path="/runs" element={<RunsPage />} />
        <Route path="/runs/:runId" element={<RunDetailsPage />} />
        <Route path="/insights" element={<InsightsPage />} />
        <Route path="/models-settings" element={<ModelsSettingsPage />} />
        <Route path="/artifacts" element={<ArtifactsPage />} />
        <Route path="/snapshots/upload" element={<SnapshotUploadPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/shortcuts" element={<ShortcutsPage />} />
        <Route path="/about" element={<AboutPage />} />
      </Route>
    </Routes>
  );
};
