import * as React from "react";
import { useState } from "react";
import { useParams } from "react-router-dom";
import { Grid, Paper, Backdrop, CircularProgress } from "@mui/material";

import K8sAppConfigurationDialog from "./K8sAppConfigurationDialog";
import K8sPodList from "./K8sPodList";

export default function K8sAppConfigurationDashboard() {
    const { appId, envId } = useParams();
    const [isLoading, setIsLoading] = useState<boolean>(false);

    return (
        <React.Fragment>
            <Grid container spacing={3}>
                {/* Configure App */}
                <Grid item xs={12}>
                    <Paper
                        sx={{ p: 2, display: "flex", flexDirection: "column" }}
                    >
                        <K8sAppConfigurationDialog
                            isLoading={isLoading}
                            setIsLoading={setIsLoading}
                        />
                    </Paper>
                </Grid>

                {/* Show Pods */}
                <Grid item xs={12}>
                    <Paper
                        sx={{ p: 2, display: "flex", flexDirection: "column" }}
                    >
                        <K8sPodList
                            appId={appId as string}
                            envId={envId as string}
                        />
                    </Paper>
                </Grid>
            </Grid>

            {/* Show Backdrop while loading */}
            {isLoading && (
                <Backdrop
                    sx={{
                        color: "#fff",
                        zIndex: (theme) => theme.zIndex.drawer + 1,
                    }}
                    open={isLoading}
                >
                    <CircularProgress color="inherit" />
                </Backdrop>
            )}
        </React.Fragment>
    );
}
