import * as React from "react";
import { useState, ChangeEvent, useEffect } from "react";
import { useParams } from "react-router-dom";

import { green, red, amber } from "@mui/material/colors";
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import {
    Accordion,
    AccordionDetails,
    AccordionSummary,
    TextField,
    Grid,
    Switch,
    Slider,
    Autocomplete,
    Button,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    FormControlLabel,
} from "@mui/material";

// Import Custom components.
import EnvVarTable, { EnvVarTableIfx } from "./EnvVarTable";
import KeyValueTable, { KeyValueTableIfx } from "./KeyValueTable";
import Title from "./Title";
import { Typography, Divider } from "@mui/material";
import {
    DeltaPatch,
    DeltaCreate,
    DeltaDelete,
    FrontendDeploymentPlan,
    AppPrimary,
    AppCanary,
    AppMetadata,
    AppSpec,
    KeyValuePairType,
    K8sEnvVar,
} from "./BackendInterfaces";

// ----------------------------------------------------------------------
// Type definitions for the various components in this very file.
// ----------------------------------------------------------------------
interface AppResourcePropIfx {
    appRes: AppPrimary | AppCanary;
    setAppRes: React.Dispatch<React.SetStateAction<AppPrimary | AppCanary>>;
}

const DefaultImages = ["nginx:1.20", "ubuntu:latest"];

// ----------------------------------------------------------------------
// Components
// ----------------------------------------------------------------------
function RequestAndLimitsComponent({ appRes, setAppRes }: AppResourcePropIfx) {
    const handleResourceSwitchChange = () => {
        setAppRes((prevObject: AppPrimary | AppCanary) => {
            let out = {
                ...prevObject,
            };
            out.deployment.useResources = !out.deployment.useResources;
            return out;
        });
    };

    const onResourceChange = (event: ChangeEvent<HTMLInputElement>) => {
        const { name, value } = event.target;
        setAppRes((prevObject: AppPrimary | AppCanary) => {
            let out = { ...prevObject };

            if (name == "cpuReq") {
                out.deployment.resources.requests.cpu = value;
            }
            if (name == "cpuLim") {
                out.deployment.resources.limits.cpu = value;
            }
            if (name == "memReq") {
                out.deployment.resources.requests.memory = value;
            }
            if (name == "memLim") {
                out.deployment.resources.limits.memory = value;
            }

            return out;
        });
    };

    return (
        <React.Fragment>
            <FormControlLabel
                control={
                    <Switch
                        checked={appRes.deployment.useResources}
                        onChange={handleResourceSwitchChange}
                    />
                }
                label="Requests & Limits"
            />
            {appRes.deployment.useResources && (
                <Grid container spacing={2} alignItems="center">
                    {/* Spacer to push text fields to the right */}
                    <Grid item xs={2} />

                    <Grid item>
                        <TextField
                            label="CPU Request"
                            variant="standard"
                            value={appRes.deployment.resources.requests.cpu}
                            name="cpuReq"
                            onChange={onResourceChange}
                        />
                    </Grid>
                    <Grid item>
                        <TextField
                            label="CPU Limit"
                            variant="standard"
                            value={appRes.deployment.resources.limits.cpu}
                            name="cpuLim"
                            onChange={onResourceChange}
                        />
                    </Grid>

                    {/* Force newline and push text fields slightly to the right*/}
                    <Grid item xs={12} />
                    <Grid item xs={2} />

                    <Grid item>
                        <TextField
                            label="Memory Request"
                            variant="standard"
                            value={appRes.deployment.resources.requests.memory}
                            name="memReq"
                            onChange={onResourceChange}
                        />
                    </Grid>
                    <Grid item>
                        <TextField
                            label="Memory Limit"
                            variant="standard"
                            value={appRes.deployment.resources.limits.memory}
                            name="memLim"
                            onChange={onResourceChange}
                        />
                    </Grid>
                </Grid>
            )}
        </React.Fragment>
    );
}

function CanaryTrafficComponent({
    appRes,
    setAppRes,
}: {
    appRes: AppCanary;
    setAppRes: React.Dispatch<React.SetStateAction<AppCanary>>;
}) {
    const onTrafficChange = (_: Event, value: number | number[]) => {
        setAppRes((prevObject: AppCanary) => {
            let out = { ...prevObject };

            // @ts-ignore
            out.trafficPercent = value;
            return out;
        });
    };

    return (
        <React.Fragment>
            <div></div>
            <Grid container spacing={2} alignItems="center">
                <Grid item xs={3}>
                    <Typography>Traffic to Canary</Typography>
                </Grid>
                <Grid item xs={9}>
                    <Slider
                        aria-label="Traffic"
                        defaultValue={0}
                        valueLabelDisplay="auto"
                        shiftStep={30}
                        step={10}
                        marks
                        min={0}
                        max={100}
                        onChange={onTrafficChange}
                    />
                </Grid>
            </Grid>
        </React.Fragment>
    );
}

function CanaryConfigComponent({
    appRes,
    setAppRes,
    envars,
    setEnvars,
    secrets,
    setSecrets,
}: {
    appRes: AppCanary;
    setAppRes: React.Dispatch<React.SetStateAction<AppCanary>>;
    envars: K8sEnvVar[];
    setEnvars: React.Dispatch<React.SetStateAction<K8sEnvVar[]>>;
    secrets: KeyValuePairType[];
    setSecrets: React.Dispatch<React.SetStateAction<KeyValuePairType[]>>;
}) {
    return (
        <React.Fragment>
            <Accordion variant="elevation">
                <AccordionSummary
                    expandIcon={<ExpandMoreIcon />}
                    aria-controls="panel1-content"
                    id="panel1-header"
                >
                    <Typography>Canary</Typography>
                </AccordionSummary>
                <AccordionDetails>
                    <div>
                        <ContainerImageComponent
                            appRes={appRes}
                            setAppRes={
                                setAppRes as React.Dispatch<React.SetStateAction<AppPrimary>>
                            }
                        />
                    </div>
                    <div>
                        <RequestAndLimitsComponent
                            appRes={appRes}
                            setAppRes={
                                setAppRes as React.Dispatch<React.SetStateAction<AppPrimary>>
                            }
                        />
                    </div>
                    <div>
                        <ServiceConfigComponent
                            appRes={appRes}
                            setAppRes={
                                setAppRes as React.Dispatch<React.SetStateAction<AppPrimary>>
                            }
                        />
                    </div>
                    <div>
                        <HealthProbeComponent
                            appRes={appRes}
                            probeKind="live"
                            setAppRes={
                                setAppRes as React.Dispatch<React.SetStateAction<AppPrimary>>
                            }
                        />
                    </div>
                    <div>
                        <HealthProbeComponent
                            appRes={appRes}
                            probeKind="ready"
                            setAppRes={
                                setAppRes as React.Dispatch<React.SetStateAction<AppPrimary>>
                            }
                        />
                    </div>
                    <div>
                        <EnvVarsComponent pairs={envars} setPairs={setEnvars} />
                    </div>
                    <div>
                        <SecretComponent pairs={secrets} setPairs={setSecrets} />
                    </div>
                    <div>
                        <CanaryTrafficComponent appRes={appRes} setAppRes={setAppRes} />
                    </div>
                </AccordionDetails>
            </Accordion>
        </React.Fragment>
    );
}

function PrimaryConfigComponent({
    appRes,
    setAppRes,
    envars,
    setEnvars,
    secrets,
    setSecrets,
}: {
    appRes: AppPrimary;
    setAppRes: React.Dispatch<React.SetStateAction<AppPrimary>>;
    envars: K8sEnvVar[];
    setEnvars: React.Dispatch<React.SetStateAction<K8sEnvVar[]>>;
    secrets: KeyValuePairType[];
    setSecrets: React.Dispatch<React.SetStateAction<KeyValuePairType[]>>;
}) {
    return (
        <React.Fragment>
            <Accordion variant="elevation">
                <AccordionSummary
                    expandIcon={<ExpandMoreIcon />}
                    aria-controls="panel1-content"
                    id="panel1-header"
                >
                    <Typography>Primary</Typography>
                </AccordionSummary>
                <AccordionDetails>
                    <div>
                        <ContainerImageComponent appRes={appRes} setAppRes={setAppRes} />
                    </div>
                    <div>
                        <RequestAndLimitsComponent appRes={appRes} setAppRes={setAppRes} />
                    </div>
                    <div>
                        <ServiceConfigComponent appRes={appRes} setAppRes={setAppRes} />
                    </div>
                    <div>
                        <HealthProbeComponent
                            appRes={appRes}
                            setAppRes={setAppRes}
                            probeKind="live"
                        />
                    </div>
                    <div>
                        <HealthProbeComponent
                            appRes={appRes}
                            setAppRes={setAppRes}
                            probeKind="ready"
                        />
                    </div>
                    <div>
                        <EnvVarsComponent pairs={envars} setPairs={setEnvars} />
                    </div>
                    <div>
                        <SecretComponent pairs={secrets} setPairs={setSecrets} />
                    </div>
                </AccordionDetails>
            </Accordion>
        </React.Fragment>
    );
}

function ContainerImageComponent({ appRes, setAppRes }: AppResourcePropIfx) {
    const onChange = (event: ChangeEvent<HTMLInputElement>) => {
        const { name, value } = event.target;
        console.log(`Update ${name}:${value}`);
        setAppRes((prevObject: AppPrimary) => {
            let out: AppPrimary = { ...prevObject };

            // @ts-ignore
            out.deployment[name] = value;
            return out;
        });
    };

    const onAutocompleteChange = (name: string, value: string) => {
        console.log(`Update ${name}:${value}`);
        setAppRes((prevObject: AppPrimary) => {
            let out: AppPrimary = { ...prevObject };

            // @ts-ignore
            out.deployment[name] = value;
            return out;
        });
    };

    return (
        <React.Fragment>
            <Grid container spacing={3} alignItems="center">
                <Grid item xs={1} /> {/* Spacer to push text fields to the right */}
                <Grid item xs={2}>
                    <Autocomplete
                        freeSolo
                        options={["main"]}
                        value={appRes.deployment.name}
                        inputValue={appRes.deployment.name}
                        onChange={(_event, value) => {
                            onAutocompleteChange("name", value || "");
                        }}
                        onInputChange={(_event, value) => {
                            onAutocompleteChange("name", value);
                        }}
                        renderInput={(params) => (
                            <TextField
                                {...params}
                                id="name"
                                label="Container Name"
                                variant="standard"
                                name="name"
                                value={appRes.deployment.name}
                                onChange={onChange}
                            />
                        )}
                    />
                </Grid>
                <Grid item xs={4}>
                    <Autocomplete
                        freeSolo
                        options={DefaultImages}
                        value={appRes.deployment.image}
                        inputValue={appRes.deployment.image}
                        onChange={(_event, value) => {
                            onAutocompleteChange("image", value || "");
                        }}
                        onInputChange={(_event, value) => {
                            onAutocompleteChange("image", value);
                        }}
                        renderInput={(params) => (
                            <TextField
                                {...params}
                                id="image"
                                label="Image:Tag"
                                variant="standard"
                                name="image"
                                value={appRes.deployment.image}
                                onChange={onChange}
                            />
                        )}
                    />
                </Grid>
                <Grid item xs={2}>
                    <Autocomplete
                        freeSolo
                        options={["bash"]}
                        value={appRes.deployment.command}
                        inputValue={appRes.deployment.command}
                        onChange={(_event, value) => {
                            onAutocompleteChange("command", value || "");
                        }}
                        onInputChange={(_event, value) => {
                            onAutocompleteChange("command", value);
                        }}
                        renderInput={(params) => (
                            <TextField
                                {...params}
                                id="command"
                                label="Optional Command"
                                variant="standard"
                                name="command"
                                value={appRes.deployment.command}
                                onChange={onChange}
                            />
                        )}
                    />
                </Grid>
                <Grid item xs={2}>
                    <Autocomplete
                        freeSolo
                        options={["-c sleep 100"]}
                        value={appRes.deployment.args}
                        inputValue={appRes.deployment.args}
                        onChange={(_event, value) => {
                            onAutocompleteChange("args", value || "");
                        }}
                        onInputChange={(_event, value) => {
                            onAutocompleteChange("args", value);
                        }}
                        renderInput={(params) => (
                            <TextField
                                {...params}
                                id="args"
                                label="Optional Args"
                                variant="standard"
                                name="args"
                                value={appRes.deployment.args}
                                onChange={onChange}
                            />
                        )}
                    />
                </Grid>
            </Grid>
        </React.Fragment>
    );
}

function HealthProbeComponent({
    appRes,
    setAppRes,
    probeKind,
}: {
    appRes: AppPrimary;
    setAppRes: React.Dispatch<React.SetStateAction<AppPrimary | AppCanary>>;
    probeKind: "live" | "ready";
}) {
    const probeType: string = probeKind == "live" ? "livenessProbe" : "readinessProbe";
    const useProbeType: string = probeKind == "live" ? "useLivenessProbe" : "useReadinessProbe";
    const labelName: string = probeKind == "live" ? "Liveness Probe" : "Readiness Probe";

    const handleSwitchChange = () => {
        setAppRes((prevObject: AppPrimary | AppCanary) => {
            let out = { ...prevObject };

            // @ts-ignore
            out.deployment[useProbeType] = !out.deployment[useProbeType];
            return out;
        });
    };

    const onHttpGetChange = (event: ChangeEvent<HTMLInputElement>) => {
        const { name, value } = event.target;
        setAppRes((prevObject: AppPrimary | AppCanary) => {
            let out = { ...prevObject };

            // @ts-ignore
            out.deployment[probeType].httpGet[name] = value;

            // @ts-ignore
            out.deployment[probeType].httpGet["scheme"] = "HTTP";

            return out;
        });
    };

    const onProbeChange = (event: ChangeEvent<HTMLInputElement>) => {
        const { name, value } = event.target;
        setAppRes((prevObject: AppPrimary | AppCanary) => {
            let out = { ...prevObject };

            // @ts-ignore
            out.deployment[probeType][name] = value;

            return out;
        });
    };

    const renderProbeFields = () => {
        // @ts-ignore
        if (!appRes.deployment[useProbeType]) return;

        return (
            <Grid container spacing={2} alignItems="center">
                {/* Spacer to push text fields to the right */}
                <Grid item xs={2} />

                <Grid item xs={2}>
                    <TextField
                        label="path"
                        variant="standard"
                        // @ts-ignore
                        value={appRes.deployment[probeType].httpGet.path}
                        name="path"
                        onChange={onHttpGetChange}
                    />
                </Grid>
                <Grid item xs={1}>
                    <TextField
                        label="port"
                        type="number"
                        variant="standard"
                        // @ts-ignore
                        value={appRes.deployment[probeType].httpGet.port}
                        name="port"
                        onChange={onHttpGetChange}
                    />
                </Grid>
                <Grid item xs={2}>
                    <TextField
                        label="successThreshold"
                        type="number"
                        variant="standard"
                        // @ts-ignore
                        value={appRes.deployment[probeType].successThreshold}
                        name="successThreshold"
                        onChange={onProbeChange}
                    />
                </Grid>
                <Grid item xs={2}>
                    <TextField
                        label="failureThreshold"
                        type="number"
                        variant="standard"
                        // @ts-ignore
                        value={appRes.deployment[probeType].failureThreshold}
                        name="failureThreshold"
                        onChange={onProbeChange}
                    />
                </Grid>
                <Grid item xs={2}>
                    <TextField
                        label="timeoutSeconds"
                        type="number"
                        variant="standard"
                        // @ts-ignore
                        value={appRes.deployment[probeType].timeoutSeconds}
                        name="timeoutSeconds"
                        onChange={onProbeChange}
                    />
                </Grid>
            </Grid>
        );
    };

    return (
        <React.Fragment>
            <FormControlLabel
                control={
                    <Switch
                        // @ts-ignore
                        checked={appRes.deployment[useProbeType]}
                        onChange={handleSwitchChange}
                    />
                }
                label={labelName}
            />
            {renderProbeFields()}
        </React.Fragment>
    );
}

function EnvVarsComponent({ pairs, setPairs }: EnvVarTableIfx) {
    return (
        <React.Fragment>
            <Accordion variant="elevation">
                <AccordionSummary
                    expandIcon={<ExpandMoreIcon />}
                    aria-controls="panel1-content"
                    id="panel1-header"
                >
                    <Typography>Environment Variables</Typography>
                </AccordionSummary>
                <AccordionDetails>
                    <EnvVarTable pairs={pairs} setPairs={setPairs} />
                </AccordionDetails>
            </Accordion>
        </React.Fragment>
    );
}

function SecretComponent({ pairs, setPairs }: KeyValueTableIfx) {
    return (
        <React.Fragment>
            <Accordion variant="elevation">
                <AccordionSummary
                    expandIcon={<ExpandMoreIcon />}
                    aria-controls="panel1-content"
                    id="panel1-header"
                >
                    <Typography>Secrets</Typography>
                </AccordionSummary>
                <AccordionDetails>
                    <KeyValueTable pairs={pairs} setPairs={setPairs} />
                </AccordionDetails>
            </Accordion>
        </React.Fragment>
    );
}

function ServiceConfigComponent({ appRes, setAppRes }: AppResourcePropIfx) {
    const handleSwitchChange = () => {
        setAppRes((prevObject: AppPrimary | AppCanary) => {
            let out = { ...prevObject };

            out.useService = !out.useService;
            return out;
        });
    };

    const onServicesChange = (event: ChangeEvent<HTMLInputElement>) => {
        const { name, value } = event.target;
        setAppRes((prevObject: AppPrimary) => {
            let out = { ...prevObject };

            // @ts-ignore
            out.service[name] = value;
            return out;
        });
    };

    return (
        <React.Fragment>
            {/* Services */}
            <FormControlLabel
                control={<Switch checked={appRes.useService} onChange={handleSwitchChange} />}
                label="Service"
            />
            {appRes.useService && (
                <Grid container spacing={2} alignItems="center">
                    {/* Spacer to push text fields to the right */}
                    <Grid item xs={2} />

                    <Grid item xs={1}>
                        <TextField
                            label="Port"
                            variant="standard"
                            value={appRes.service.port}
                            fullWidth
                            name="port"
                            onChange={onServicesChange}
                        />
                    </Grid>
                    <Grid item xs={1}>
                        <TextField
                            label="Target Port"
                            variant="standard"
                            value={appRes.service.targetPort}
                            fullWidth
                            name="targetPort"
                            onChange={onServicesChange}
                        />
                    </Grid>
                </Grid>
            )}
        </React.Fragment>
    );
}

function ShowPlanComponent({
    isOpen,
    setIsOpen,
    deploymentPlan,
    showJobProgress,
}: {
    isOpen: boolean;
    setIsOpen: React.Dispatch<React.SetStateAction<boolean>>;
    deploymentPlan: FrontendDeploymentPlan;
    showJobProgress: Function;
}) {
    const onCancel = () => setIsOpen(false);
    const onSubmit = () => {
        showJobProgress(deploymentPlan.jobId);
    };

    const renderPatch = (el: DeltaPatch) => {
        const key = el.meta.kind + el.meta.namespace + el.meta.name;

        const renderDiff = (line: string, index: number) => {
            if (line.startsWith("+")) {
                return (
                    <Typography
                        key={key + index}
                        sx={{
                            color: green[500],
                            whiteSpace: "pre-wrap",
                            fontFamily: "monospace",
                        }}
                    >
                        {line}
                    </Typography>
                );
            } else if (line.startsWith("-")) {
                return (
                    <Typography
                        key={key + index}
                        sx={{
                            color: red[500],
                            whiteSpace: "pre-wrap",
                            fontFamily: "monospace",
                        }}
                    >
                        {line}
                    </Typography>
                );
            } else {
                return (
                    <Typography
                        key={key + index}
                        sx={{ whiteSpace: "pre-wrap", fontFamily: "monospace" }}
                    >
                        {line}
                    </Typography>
                );
            }
        };

        let out: JSX.Element[] = [];
        out.push(
            <Typography key={key} sx={{ color: amber[500] }}>
                Patch {el.meta.kind.toUpperCase()} {el.meta.namespace}/{el.meta.name}
            </Typography>,
        );
        out.push(...el.diff.split("\n").map(renderDiff));
        out.push(<Divider key={key + "sep"} />);
        return out;
    };

    const renderCreate = (el: DeltaCreate) => {
        const key = el.meta.kind + el.meta.namespace + el.meta.name;

        // Header element, eg "Add DEPLOYMENT default/myapp"
        let out: JSX.Element[] = [];
        out.push(
            <Typography key={key} sx={{ color: green[500] }}>
                Add {el.meta.kind.toUpperCase()} {el.meta.namespace}/{el.meta.name}
            </Typography>,
        );

        // Convert manifest to string and display each line in green.
        const jsManifest = JSON.stringify(el.manifest, null, 4);
        const tmp = jsManifest.split("\n").map((line, index) => (
            <Typography key={key + index} sx={{ color: green[500], whiteSpace: "pre-wrap" }}>
                {" "}
                {line}
            </Typography>
        ));
        out.push(...tmp);
        out.push(<Divider key={key + "sep"} />);

        return out;
    };

    const renderDelete = (el: DeltaDelete) => {
        const key = el.meta.kind + el.meta.namespace + el.meta.name;

        // Header element, eg "Delete DEPLOYMENT default/myapp"
        return (
            <Typography key={key} sx={{ color: red[500] }}>
                Delete {el.meta.kind.toUpperCase()} {el.meta.namespace}/{el.meta.name}
            </Typography>
        );
    };

    const formatDiff = () => {
        let out: JSX.Element[] = [];

        for (const el of deploymentPlan.create) {
            out.push(...renderCreate(el));
        }

        for (const el of deploymentPlan.patch) {
            out.push(...renderPatch(el));
        }

        for (const el of deploymentPlan.delete) {
            out.push(renderDelete(el));
        }

        const toAdd = `${deploymentPlan.create.length} to add`;
        const toMod = `${deploymentPlan.patch.length} to modify`;
        const toDel = `${deploymentPlan.delete.length} to delete`;

        out.push(<Divider key={"summary-sep-1"} style={{ marginBottom: "20px" }} />);
        out.push(
            <Typography component="div" variant="body1" key="summary">
                <span style={{ color: "inherit", marginRight: "25px" }}>Plan:</span>
                <span
                    style={{
                        color: deploymentPlan.create.length ? "green" : "inherit",
                        marginRight: "25px",
                    }}
                >
                    {toAdd}
                </span>
                <span
                    style={{
                        color: deploymentPlan.patch.length ? "orange" : "inherit",
                        marginRight: "25px",
                    }}
                >
                    {toMod}
                </span>
                <span
                    style={{
                        color: deploymentPlan.delete.length ? "red" : "inherit",
                        marginRight: "25px",
                    }}
                >
                    {toDel}
                </span>
            </Typography>,
        );
        return out;
    };
    const formattedDiffText = formatDiff();

    return (
        <Dialog
            open={isOpen}
            onClose={onCancel}
            scroll="paper"
            aria-labelledby="scroll-dialog-title"
            aria-describedby="scroll-dialog-description"
            fullWidth={true}
            maxWidth="xl"
        >
            <DialogTitle id="scroll-dialog-title">Diff</DialogTitle>
            <DialogContent
                sx={{
                    overflowY: "auto",
                    maxHeight: "300px", // Max height before we get scroll bars.
                }}
            >
                {formattedDiffText}
            </DialogContent>
            <DialogActions>
                <Button onClick={onCancel}>Cancel</Button>
                <Button onClick={onSubmit}>Submit</Button>
            </DialogActions>
        </Dialog>
    );
}

function JobStatusComponent({
    isOpen,
    setIsOpen,
    jobId,
}: {
    isOpen: boolean;
    setIsOpen: React.Dispatch<React.SetStateAction<boolean>>;
    jobId: number;
}) {
    const [success, setSuccess] = useState<boolean>(false);

    const onClose = () => setIsOpen(false);

    const sendData = () => {
        const data = { jobId: jobId };
        fetch(`/demo/api/crt/v1/jobs`, {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
            },
            body: JSON.stringify(data),
        })
            .then((response) => {
                if (!response.ok) {
                    throw new Error(`HTTP error! Status: ${response.status}`);
                }
                return response.json();
            })
            .then((_) => {
                setSuccess(true);
            })
            .catch((error) => {
                console.error("Error fetching job data:", error);
                setSuccess(false);
            });
    };

    useEffect(() => {
        if (isOpen) {
            sendData(); // Make initial POST request if the dialog is open and the job is not done
        }
    }, [isOpen, jobId]);

    const formatContent = () => {
        if (success) {
            return (
                <Typography key="jobid" sx={{ color: green[500] }}>
                    Success
                </Typography>
            );
        } else {
            return (
                <Typography key="jobid" sx={{ color: red[500] }}>
                    Error
                </Typography>
            );
        }
    };

    return (
        <Dialog
            open={isOpen}
            onClose={onClose}
            scroll="paper"
            aria-labelledby="scroll-dialog-title"
            aria-describedby="scroll-dialog-description"
            sx={{ minWidth: "400px" }}
        >
            <DialogTitle id="scroll-dialog-title">Job</DialogTitle>
            <DialogContent
                sx={{
                    overflowY: "auto",
                    maxHeight: "300px", // Max height before we get scroll bars.
                }}
            >
                <Typography key={jobId}>ID: {jobId}</Typography>
                {formatContent()}
            </DialogContent>
            <DialogActions>
                <Button onClick={onClose}>Close</Button>
            </DialogActions>
        </Dialog>
    );
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
            httpGet: { path: "/ready", port: 8080, scheme: "HTTP" },
            initialDelaySeconds: 10,
            periodSeconds: 20,
            timeoutSeconds: 1,
            successThreshold: 1,
            failureThreshold: 1,
        },
        useReadinessProbe: true,
        livenessProbe: {
            httpGet: { path: "/live", port: 8080, scheme: "HTTP" },
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
        name: "main",
        command: "",
        args: "",
    },
    service: {
        port: 8080,
        targetPort: 8080,
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
            httpGet: { path: "/ready", port: 8080, scheme: "HTTP" },
            initialDelaySeconds: 10,
            periodSeconds: 20,
            timeoutSeconds: 1,
            successThreshold: 1,
            failureThreshold: 1,
        },
        useReadinessProbe: true,
        livenessProbe: {
            httpGet: { path: "/live", port: 8080, scheme: "HTTP" },
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
        port: 8080,
        targetPort: 8080,
    },
    useService: false,
    hpa: {
        name: "",
    },
    trafficPercent: 0,
};

const initDeploymentPlan = {
    jobId: 10,
    create: [],
    patch: [],
    delete: [],
};

export default function K8sAppConfigurationDialog({
    isLoading,
    setIsLoading,
}: {
    isLoading: boolean;
    setIsLoading: React.Dispatch<React.SetStateAction<boolean>>;
}) {
    const { appId, envId } = useParams();

    const [primaryEnvars, setPrimaryEnvars] = useState<K8sEnvVar[]>([]);
    const [canaryEnvars, setCanaryEnvars] = useState<K8sEnvVar[]>([]);

    const [primarySecrets, setPrimarySecrets] = useState<KeyValuePairType[]>([]);
    const [canarySecrets, setCanarySecrets] = useState<KeyValuePairType[]>([]);

    const [primary, setPrimary] = useState<AppPrimary>(initialAppPrimary);
    const [canary, setCanary] = useState<AppCanary>(initialAppCanary);

    const [metaInfo, setMetaInfo] = useState<AppMetadata>({
        name: "",
        env: "",
        namespace: "",
    });

    const [isPlanModalOpen, setIsPlanModalOpen] = useState(false);
    const [isProgressModalOpen, setIsProgressModalOpen] = useState(false);
    const [jobId, setJobId] = useState(0);
    const [deploymentPlan, setDeploymentPlan] = useState(initDeploymentPlan);

    const [hasCanary, setHasCanary] = useState<boolean>(false);

    const onUpdateFlux = () => {
        setPrimary((prevObject: AppPrimary) => ({
            ...prevObject,
            isFlux: !prevObject.deployment.isFlux,
        }));
    };

    const onAddCanary = () => {
        setHasCanary(!hasCanary);
    };

    useEffect(() => {
        const fetchData = async () => {
            // setIsLoading(true)
            try {
                const response = await fetch(`/demo/api/crt/v1/apps/${appId}/${envId}`);
                const data: AppSpec = await response.json();
                console.log("From backend:", data);

                // Update state using the setter functions.
                setPrimary(() => data.primary);
                setCanary(() => data.canary);
                setMetaInfo(() => data.metadata);
                setHasCanary(() => data.hasCanary);
                setPrimaryEnvars(() => data.primary.deployment.envVars);
                setCanaryEnvars(() => data.canary.deployment.envVars);
            } catch (error) {
                console.error("Error fetching data:", error);
            } finally {
                setIsLoading(false);
            }
        };

        // Fetch data initially when the component mounts.
        fetchData();
    }, []);

    const onClickDelete = async () => {
        setIsLoading(true);

        try {
            const response = await fetch(`/demo/api/crt/v1/apps/${metaInfo.name}/${metaInfo.env}`, {
                method: "DELETE",
                headers: {
                    "Content-Type": "application/json",
                },
            });

            if (!response.ok) {
                throw new Error("Failed to fetch");
            }

            setDeploymentPlan(await response.json());
            setIsPlanModalOpen(true);
        } catch (error) {
            console.error("Error posting data:", error);
        }
        setIsLoading(false);
    };

    // Send the current app configuration to the backend and request a plan. Then insert the plan
    // into the `setDeploymentPlan` state variable and activate the modal that shows it.
    const onClickApply = async () => {
        setIsLoading(true);
        let data: AppSpec = {
            primary: primary,
            canary: canary,
            metadata: metaInfo,
            hasCanary: hasCanary,
        };

        // Merge the state variables for the environment variable back into the payload.
        primary.deployment.envVars = primaryEnvars;
        canary.deployment.envVars = canaryEnvars;

        console.log("To backend: ", data);
        try {
            const response = await fetch(`/demo/api/crt/v1/apps/${metaInfo.name}/${metaInfo.env}`, {
                method: "PATCH",
                headers: {
                    "Content-Type": "application/json",
                },
                body: JSON.stringify(data),
            });

            if (!response.ok) {
                throw new Error("Failed to fetch");
            }

            setDeploymentPlan(await response.json());
            setIsPlanModalOpen(true);
        } catch (error) {
            console.error("Error posting data:", error);
        }
        setIsLoading(false);
    };

    // Close the Plan confirmation dialog and open the progress dialog.
    const showJobProgress = (jobId: number) => {
        setIsPlanModalOpen(false);
        setJobId(jobId);
        setIsProgressModalOpen(true);
    };

    return (
        <React.Fragment>
            <Title>
                {appId} ({envId})
            </Title>

            {/* Flux */}
            <FormControlLabel
                control={<Switch checked={primary.deployment.isFlux} onChange={onUpdateFlux} />}
                label="Flux"
            />
            <FormControlLabel
                control={<Switch checked={hasCanary} onChange={onAddCanary} />}
                label="Canary"
            />

            <PrimaryConfigComponent
                appRes={primary}
                setAppRes={setPrimary}
                envars={primaryEnvars}
                setEnvars={setPrimaryEnvars}
                secrets={primarySecrets}
                setSecrets={setPrimarySecrets}
            />
            {hasCanary && (
                <CanaryConfigComponent
                    appRes={canary}
                    setAppRes={setCanary}
                    envars={canaryEnvars}
                    setEnvars={setCanaryEnvars}
                    secrets={canarySecrets}
                    setSecrets={setCanarySecrets}
                />
            )}

            <ShowPlanComponent
                isOpen={isPlanModalOpen}
                setIsOpen={setIsPlanModalOpen}
                deploymentPlan={deploymentPlan}
                showJobProgress={showJobProgress}
            />
            <JobStatusComponent
                isOpen={isProgressModalOpen}
                setIsOpen={setIsProgressModalOpen}
                jobId={jobId}
            />

            {/* Cancel/Apply button to request a plan from the backend.*/}
            <p />
            <Grid container spacing={2} alignItems="center" justifyContent="space-between">
                <Grid item>
                    <Button
                        variant="contained"
                        style={{ backgroundColor: "#ff0000", color: "#fff" }}
                        onClick={onClickDelete}
                    >
                        Delete
                    </Button>
                </Grid>
                <Grid item>
                    <Button variant="contained" color="primary" onClick={onClickApply}>
                        Apply
                    </Button>
                </Grid>
            </Grid>
        </React.Fragment>
    );
}
