import React from "react";
import { Navigate, useLocation, Outlet } from "react-router-dom";
import { getAuthToken } from "../lib/api";

export default function ProtectedRoute({ children }) {
    const token = getAuthToken();
    const location = useLocation();

    if (!token) {
        return <Navigate to="/login" state={{ from: location }} replace />;
    }

    return children ? children : <Outlet />;
}
