import { Navigate, Route, Routes } from 'react-router-dom';
import { SessionProvider } from './app/SessionContext';
import { AppShell } from './components/AppShell';
import { RequireAuth } from './components/RequireAuth';
import { CaseLibraryPage } from './pages/CaseLibraryPage';
import { CasesPage } from './pages/CasesPage';
import { CicdPage } from './pages/CicdPage';
import { DashboardPage } from './pages/DashboardPage';
import { FunctionalAutomationPage } from './pages/FunctionalAutomationPage';
import { IssuesPage } from './pages/IssuesPage';
import { LoginPage } from './pages/LoginPage';
import { PlansPage } from './pages/PlansPage';
import { PerformanceAutomationPage } from './pages/PerformanceAutomationPage';
import { RunExecutionPage } from './pages/RunExecutionPage';
import { SettingsPage } from './pages/SettingsPage';
import { SuitesPage } from './pages/SuitesPage';

export default function App() {
  return (
    <SessionProvider>
      <Routes>
        <Route path="/login" element={<LoginPage />} />

        <Route element={<RequireAuth />}>
          <Route element={<AppShell />}>
            <Route path="/" element={<DashboardPage />} />
            <Route path="/case-library" element={<CaseLibraryPage />} />
            <Route path="/cases" element={<CasesPage />} />
            <Route path="/suites" element={<SuitesPage />} />
            <Route path="/plans" element={<PlansPage />} />
            <Route path="/runs/:runKey" element={<RunExecutionPage />} />
            <Route path="/issues" element={<IssuesPage />} />
            <Route path="/cicd" element={<CicdPage />} />
            <Route path="/perf-automation" element={<PerformanceAutomationPage />} />
            <Route path="/func-automation" element={<FunctionalAutomationPage />} />
            <Route path="/settings" element={<SettingsPage />} />
          </Route>
        </Route>

        <Route path="*" element={<Navigate to="/" replace />} />
      </Routes>
    </SessionProvider>
  );
}
