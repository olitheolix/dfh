import * as React from 'react';
import * as ReactDOM from 'react-dom/client';
import { ThemeProvider } from '@emotion/react';
import { CssBaseline } from '@mui/material';
import theme from './theme';
import ErrorPage from "./error-page";
import Dashboard from "./Dashboard";

import ClusterOverview from './ClusterOverview';
import K8sAppConfigurationDashboard from './K8sAppConfigurationDashboard';


import {
    createBrowserRouter,
    RouterProvider,
} from "react-router-dom";


const router = createBrowserRouter([
    {
        path: "/",
        element: <Dashboard />,
        errorElement: <ErrorPage />,
        children: [
            {
                path: "/",
                element: <ClusterOverview />,
            },
            {
                path: "app/:appId/:envId",
                element: <K8sAppConfigurationDashboard />,
            }
        ]
    },
]);

ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
        <ThemeProvider theme={theme}>
            <CssBaseline />
            <RouterProvider router={router} />
        </ThemeProvider>
    </React.StrictMode>,
);
