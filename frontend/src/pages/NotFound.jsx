import React from "react";
import { Link } from "react-router-dom";
import { House, ArrowLeft } from "@phosphor-icons/react";
import { Button } from "../components/ui/button";

export default function NotFound() {
    return (
        <div className="min-h-screen bg-slate-950 text-slate-100 flex flex-col items-center justify-center p-6 text-center" data-testid="not-found-page">
            <div className="w-16 h-16 rounded-2xl bg-amber-400/10 border border-amber-400/20 grid place-items-center mb-6">
                <House size={32} weight="fill" className="text-amber-400" />
            </div>
            <span className="text-xs font-mono uppercase tracking-[0.24em] text-amber-400 mb-2">Error 404</span>
            <h1 className="text-4xl font-serif font-medium text-slate-100 mb-3">Property or Page Not Found</h1>
            <p className="text-sm text-slate-400 max-w-md mb-8">
                The requested resource does not exist in the EstateX portfolio or may have been relocated.
            </p>
            <div className="flex items-center gap-4">
                <Link to="/app">
                    <Button className="bg-amber-400 hover:bg-amber-300 text-slate-950 font-semibold">
                        <ArrowLeft size={16} weight="bold" className="mr-2" /> Return to Pipeline
                    </Button>
                </Link>
                <Link to="/">
                    <Button variant="outline" className="border-slate-800 text-slate-300 hover:bg-slate-900 hover:text-slate-100">
                        Public Landing
                    </Button>
                </Link>
            </div>
        </div>
    );
}
