import { BrowserRouter, Routes, Route } from "react-router-dom";
import { Toaster } from "sonner";
import Layout from "./components/Layout";
import ProtectedRoute from "./components/ProtectedRoute";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import Dashboard from "./pages/Dashboard";
import LeadDetail from "./pages/LeadDetail";
import Analytics from "./pages/Analytics";
import Capture from "./pages/Capture";
import Compare from "./pages/Compare";
import NotFound from "./pages/NotFound";
import "./App.css";

function App() {
    return (
        <div className="App dark" data-testid="app-root">
            <BrowserRouter>
                <Routes>
                    {/* Public Routes */}
                    <Route path="/" element={<Landing />} />
                    <Route path="/capture" element={<Capture />} />
                    <Route path="/login" element={<Login />} />

                    {/* Protected Concierge Pipeline Routes */}
                    <Route element={<ProtectedRoute><Layout /></ProtectedRoute>}>
                        <Route path="/app" element={<Dashboard />} />
                        <Route path="/leads/:id" element={<LeadDetail />} />
                        <Route path="/analytics" element={<Analytics />} />
                        <Route path="/compare" element={<Compare />} />
                    </Route>

                    {/* 404 Catch-All */}
                    <Route path="*" element={<NotFound />} />
                </Routes>
            </BrowserRouter>
            <Toaster
                theme="dark"
                position="bottom-right"
                toastOptions={{
                    style: {
                        background: "rgba(15,23,42,0.85)",
                        border: "1px solid rgba(148,163,184,0.15)",
                        backdropFilter: "blur(16px)",
                        color: "#f8fafc",
                    },
                }}
            />
        </div>
    );
}

export default App;
