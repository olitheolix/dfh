import * as React from "react";
import { useNavigate } from "react-router-dom";
import { useState, ChangeEvent } from "react";
import { MenuItem, Select } from "@mui/material";
import {
    TextField,
    Grid,
    Button,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
} from "@mui/material";

// Import Custom components.
import Title from "./Title";
import { Paper, Typography } from "@mui/material";
import { AppPrimary, AppCanary, AppMetadata, AppSpec } from "./BackendInterfaces";

function CreateAppComponent({
    meta,
    setMeta,
}: {
    meta: AppMetadata;
    setMeta: React.Dispatch<React.SetStateAction<AppMetadata>>;
}) {
    const onChange = (event: ChangeEvent<HTMLInputElement>) => {
        const { name, value } = event.target;
        setMeta((prevObject: AppMetadata) => {
            let out = { ...prevObject };

            // @ts-ignore
            out[name] = value;

            return out;
        });
    };

    const renderProbeFields = () => {
        return (
            <Grid container spacing={2} alignItems="center">
                {/* Spacer to push text fields to the right */}
                <Grid item xs={2} />

                <Grid item xs={2}>
                    <TextField
                        label="name"
                        type="string"
                        variant="standard"
                        // @ts-ignore
                        value={meta.name}
                        name="name"
                        onChange={onChange}
                    />
                </Grid>
                <Grid item xs={2}>
                    <TextField
                        label="namespace"
                        type="string"
                        variant="standard"
                        // @ts-ignore
                        value={meta.namespace}
                        name="namespace"
                        onChange={onChange}
                    />
                </Grid>
                <Grid item xs={2}>
                    <TextField
                        label="environment"
                        type="string"
                        variant="standard"
                        // @ts-ignore
                        value={meta.env}
                        name="env"
                        onChange={onChange}
                    />
                </Grid>
            </Grid>
        );
    };

    return <React.Fragment>{renderProbeFields()}</React.Fragment>;
}

const initialAppPrimary: AppPrimary = {
    deployment: {
        isFlux: false,
        resources: {
            requests: {
                cpu: "100m",
                memory: "128M",
            },
            limits: {
                cpu: "100m",
                memory: "128M",
            },
        },
        useResources: true,
        readinessProbe: {
            httpGet: { path: "/ready", port: 8080 },
            initialDelaySeconds: 10,
            periodSeconds: 20,
            timeoutSeconds: 1,
            successThreshold: 1,
            failureThreshold: 1,
        },
        useReadinessProbe: true,
        livenessProbe: {
            httpGet: { path: "/live", port: 8080 },
            initialDelaySeconds: 10,
            periodSeconds: 20,
            timeoutSeconds: 1,
            successThreshold: 1,
            failureThreshold: 1,
        },
        useLivenessProbe: true,
        secrets: [],
        envVars: [],
        image: "",
        name: "",
        command: "",
        args: "",
    },
    service: {
        port: 0,
        targetPort: 0,
    },
    useService: false,
    hpa: {
        name: "",
    },
};

const initialAppCanary: AppCanary = {
    deployment: {
        isFlux: false,
        resources: {
            requests: {
                cpu: "100m",
                memory: "128M",
            },
            limits: {
                cpu: "100m",
                memory: "128M",
            },
        },
        useResources: true,
        readinessProbe: {
            httpGet: { path: "/ready", port: 8080 },
            initialDelaySeconds: 10,
            periodSeconds: 20,
            timeoutSeconds: 1,
            successThreshold: 1,
            failureThreshold: 1,
        },
        useReadinessProbe: true,
        livenessProbe: {
            httpGet: { path: "/live", port: 8080 },
            initialDelaySeconds: 10,
            periodSeconds: 20,
            timeoutSeconds: 1,
            successThreshold: 1,
            failureThreshold: 1,
        },
        useLivenessProbe: true,
        secrets: [],
        envVars: [],
        image: "",
        name: "",
        command: "",
        args: "",
    },
    service: {
        port: 0,
        targetPort: 0,
    },
    useService: false,
    hpa: {
        name: "",
    },
    trafficPercent: 0,
};

const DropdownComponent = () => {
    const [selectedItem, setSelectedItem] = React.useState("");

    const handleChange = (event: any) => {
        setSelectedItem(event.target.value);
    };

    return (
        <div>
            <Select value={selectedItem} onChange={handleChange} fullWidth>
                <MenuItem value={"Backend"}>Backend</MenuItem>
                <MenuItem value={"Frontend"}>Frontend</MenuItem>
                <MenuItem value={"Infra"}>Infra</MenuItem>
            </Select>
        </div>
    );
};

export default function K8sNewAppDialog() {
    const navigate = useNavigate();

    const [meta, setMeta] = useState<AppMetadata>({
        name: "",
        namespace: "",
        env: "",
    });
    const [dialogOpen, setDialogOpen] = useState(false);

    const handleCloseDialog = () => {
        setDialogOpen(false);
    };

    // Send the current app configuration to the backend and request a plan. Then insert the plan
    // into the `setDeploymentPlan` state variable and activate the modal that shows it.
    const onClickApply = async () => {
        let data: AppSpec = {
            primary: initialAppPrimary,
            canary: initialAppCanary,
            metadata: meta,
            hasCanary: false,
        };

        console.log("To backend: ", data);
        try {
            const response = await fetch(`/demo/api/crt/v1/apps/${meta.name}/${meta.env}`, {
                method: "POST",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(data),
            });

            if (!response.ok) {
                throw new Error("Failed to make DELETE request");
            }
            navigate(`/app/${meta.name}/${meta.env}`);
        } catch (error) {
            setDialogOpen(true);
            console.error("App already exists:", error);
        }
    };

    return (
        <React.Fragment>
            <Paper
                style={{
                    padding: "20px",
                    display: "flex",
                    flexDirection: "column",
                }}
            >
                <Title>Create New Application</Title>

                <Grid container spacing={2} alignItems="left" justifyContent="left">
                    <Grid item xs={4}>
                        <Typography>Project</Typography>
                        <DropdownComponent />
                    </Grid>
                    <Grid item xs={12}>
                        <CreateAppComponent meta={meta} setMeta={setMeta} />
                    </Grid>
                </Grid>

                {/* Cancel/Apply button to request a plan from the backend.*/}
                <p />
                <Grid container alignItems="center" justifyContent="right">
                    <Grid item>
                        <Button variant="contained" color="primary" onClick={onClickApply}>
                            Create
                        </Button>
                    </Grid>
                </Grid>

                {/* Display Error Dialog for when the app could not be created. */}
                <Dialog open={dialogOpen} onClose={handleCloseDialog}>
                    <DialogTitle>Error</DialogTitle>
                    <DialogContent>
                        <p>Failed to fetch data. Please try again later.</p>
                    </DialogContent>
                    <DialogActions>
                        <Button onClick={handleCloseDialog} color="primary">
                            Close
                        </Button>
                    </DialogActions>
                </Dialog>
            </Paper>
        </React.Fragment>
    );
}
