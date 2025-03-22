import * as React from "react";
import * as ReactDOM from "react-dom/client";
import { ThemeProvider } from "@emotion/react";
import { CssBaseline } from "@mui/material";
import theme from "./theme";
import ErrorPage from "./error-page";
import Dashboard from "./Dashboard";

import Workspaces from "./Workspaces";
import { HTTPErrorProvider } from "./WebRequests";

import { createBrowserRouter, RouterProvider } from "react-router-dom";

const router = createBrowserRouter(
    [
        {
            path: "/",
            element: <Dashboard />,
            errorElement: <ErrorPage />,
            children: [
                {
                    path: "/",
                    element: <Workspaces />,
                },
                {
                    path: "workspaces/",
                    element: <Workspaces />,
                },
            ],
        },
    ],
    {
        basename: "/demo",
    },
);

ReactDOM.createRoot(document.getElementById("root")!).render(
    <React.StrictMode>
        <HTTPErrorProvider>
            <ThemeProvider theme={theme}>
                <CssBaseline />
                <RouterProvider router={router} />
            </ThemeProvider>
        </HTTPErrorProvider>
    </React.StrictMode>,
);
