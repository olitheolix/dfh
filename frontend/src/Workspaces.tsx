import React from "react";
import Switch from "@mui/material/Switch";
import { useState, useEffect, useRef, useContext } from "react";
import { DataGrid, GridEventListener, GridToolbar } from "@mui/x-data-grid";
import { Box, Paper, FormControlLabel, Typography } from "@mui/material";
import { WorkspaceInfo, WorkspaceResource, DGWorkspaceRow, DGResourceRow } from "./UAMInterfaces";
import Grid from "@mui/material/Grid2";
import Title from "./Title";
import { httpGet, HTTPErrorContext, HTTPErrorContextType } from "./WebRequests";
import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import CancelIcon from "@mui/icons-material/Cancel";
import { green, red } from "@mui/material/colors";
import Link from "@mui/material/Link";
import { useSearchParams } from "react-router-dom";

const DataGridWorkspaceColumns = [
    {
        field: "ok",
        headerName: "",
        width: 20,
        renderCell: (params: any) => (
            <div
                style={{
                    display: "flex",
                    alignItems: "center",
                    height: "100%",
                }}
            >
                {params.value ? (
                    <CheckCircleIcon sx={{ color: green[500] }} />
                ) : (
                    <CancelIcon sx={{ color: red[500] }} />
                )}
            </div>
        ),
    },
    { field: "name", headerName: "Name", flex: 1 },
];
const DataGridResourceColumns = [
    {
        field: "ok",
        headerName: "",
        width: 20,
        renderCell: (params: any) => (
            <div
                style={{
                    display: "flex",
                    alignItems: "center",
                    height: "100%",
                }}
            >
                {params.value ? (
                    <CheckCircleIcon sx={{ color: green[500] }} />
                ) : (
                    <CancelIcon sx={{ color: red[500] }} />
                )}
            </div>
        ),
    },
    { field: "name", headerName: "Name", width: 200 },
    { field: "kind", headerName: "Kind", width: 200 },
    { field: "groupversion", headerName: "Group", width: 300 },
    { field: "namespace", headerName: "Namespace", width: 100 },
    {
        field: "linkGCPLogs",
        headerName: "GCP",
        width: 150,
        renderCell: (params: any) => (
            <div>
                <Link href={params.row.linkGCPObject} target="_blank" rel="noopener">
                    Obj
                </Link>
                {"\u00A0"}|{"\u00A0"}
                <Link href={params.row.linkGCPLogs} target="_blank" rel="noopener">
                    Logs
                </Link>
                {"\u00A0"}|{"\u00A0"}
                <Link
                    href={`/demo/api/uam/v1/workspaces/json?${params.row.linkJSON}`}
                    target="_blank"
                    rel="noopener"
                >
                    JSON
                </Link>
            </div>
        ),
    },
    { field: "status", headerName: "Status", flex: 1 },
];

// Show a paper with Workspace information.
function WorkspaceInfoPaper({ selectedWorkspace }: { selectedWorkspace: DGWorkspaceRow }) {
    return (
        <Paper
            style={{
                padding: "20px",
                display: "flex",
                flexDirection: "column",
            }}
            sx={{ mt: 0, mb: 6 }}
        >
            <Title>
                <Box display="flex" justifyContent="space-between" alignItems="center">
                    Workspace {selectedWorkspace.name}
                </Box>
            </Title>

            <Typography variant="subtitle1" gutterBottom>
                Owner: {selectedWorkspace.owner}
            </Typography>
            <Typography variant="subtitle1" gutterBottom>
                Owner: {selectedWorkspace.owner}
            </Typography>
        </Paper>
    );
}

function ResourceGrid({ selectedWorkspace }: { selectedWorkspace: DGWorkspaceRow }) {
    const [errSwitch, setErrSwitch] = useState<boolean>(false);
    const [filteredRows, setFilteredRows] = useState<DGResourceRow[]>([]);
    const [errCtx, _] = React.useState<HTTPErrorContextType>(useContext(HTTPErrorContext));
    const [resourceRows, setResourceRows] = useState<DGResourceRow[]>([]);
    const [loading, setLoading] = useState<boolean>(false);

    const prevSelection = useRef("");

    // Populate the workspaces upon mounting the component.
    useEffect(() => {
        if (errSwitch) {
            setFilteredRows(resourceRows.filter((item) => !item.ok));
        } else {
            setFilteredRows(resourceRows);
        }
    }, [resourceRows, errSwitch]);

    useEffect(() => {
        if (selectedWorkspace.name != "") {
            if (prevSelection.current !== selectedWorkspace.name) {
                prevSelection.current = selectedWorkspace.name;
                setFilteredRows([]);
                setLoading(true);
                loadWorkspaceResources(selectedWorkspace.name);
                setLoading(false);
            }
        }
    }, [selectedWorkspace]);

    const loadWorkspaceResources = async (name: string) => {
        const ret = await httpGet(`/demo/api/uam/v1/workspaces/resources/${name}`);
        if (ret.err) {
            errCtx.showError(ret.err);
            return;
        }
        const rowData = ret.data.map((ws: WorkspaceResource) => {
            return {
                id: `${ws.group}/${ws.version}/${ws.kind}/${ws.namespace}/${ws.name}`,
                groupversion: `${ws.group}/${ws.version}`,
                ...ws,
            } as DGResourceRow;
        });
        setResourceRows(rowData);
    };

    return (
        <Paper
            style={{
                padding: "20px",
                display: "flex",
                flexDirection: "column",
            }}
        >
            <Title>Resources in {selectedWorkspace.name}</Title>
            <Box height="70vh">
                <DataGrid
                    disableColumnSelector
                    rows={filteredRows}
                    columns={DataGridResourceColumns}
                    keepNonExistentRowsSelected={false}
                    loading={loading}
                    initialState={{
                        sorting: {
                            sortModel: [{ field: "name", sort: "asc" }],
                        },
                    }}
                    slots={{ toolbar: GridToolbar }}
                    slotProps={{
                        toolbar: {
                            showQuickFilter: true,
                        },
                        loadingOverlay: {
                            variant: "linear-progress",
                            noRowsVariant: "linear-progress",
                        },
                    }}
                />
            </Box>
            <FormControlLabel
                control={<Switch checked={errSwitch} onChange={() => setErrSwitch(!errSwitch)} />}
                label="Errors Only"
            />
        </Paper>
    );
}

function WorkspaceGrid({
    selectedWorkspace,
    setSelectedWorkspace,
}: {
    selectedWorkspace: DGWorkspaceRow;
    setSelectedWorkspace: React.Dispatch<React.SetStateAction<DGWorkspaceRow>>;
}) {
    const [loading, setLoading] = useState<boolean>(true);
    const [filteredRows, setFilteredRows] = useState<DGWorkspaceRow[]>([]);
    const [errSwitch, setErrSwitch] = useState<boolean>(false);
    const [wsRows, setWsRows] = useState<DGWorkspaceRow[]>([]);
    const [errCtx, _] = React.useState<HTTPErrorContextType>(useContext(HTTPErrorContext));
    const [searchParams, setSearchParams] = useSearchParams();

    // Populate the workspaces upon mounting the component.
    useEffect(() => {
        loadWorkspaces();
    }, [searchParams]);

    const loadWorkspaces = async () => {
        const ret = await httpGet("/demo/api/uam/v1/workspaces/info");
        setLoading(false);

        if (ret.err) {
            errCtx.showError(ret.err);
            return;
        }

        var data = ret.data.map((group: WorkspaceInfo) => {
            return { id: group.name, ...group } as DGWorkspaceRow;
        });

        setWsRows(data);
    };

    // Load the workspace resources when the user clicks on row in the left
    // Workspace grid.
    const handleWorkspaceRowClick: GridEventListener<"rowClick"> = async (params) => {
        setSelectedWorkspace(params.row);
        setSearchParams({ id: params.row.id });
    };

    useEffect(() => {
        if (errSwitch) {
            setFilteredRows(wsRows.filter((item) => !item.ok));
        } else {
            setFilteredRows(wsRows);
        }

        const idFromUrl = searchParams.get("id");
        if (idFromUrl) {
            const selected = filteredRows.filter((row) => row.name == idFromUrl);
            if (selected.length > 0) {
                setSelectedWorkspace(selected[0]);
            }
        }
    }, [wsRows, errSwitch]);

    return (
        <div>
            <Title>Workspaces</Title>
            <Box sx={{ flexGrow: 1 }}>
                <DataGrid
                    disableColumnSelector
                    rows={filteredRows}
                    columns={DataGridWorkspaceColumns}
                    slots={{ toolbar: GridToolbar }}
                    onRowClick={handleWorkspaceRowClick}
                    keepNonExistentRowsSelected={false}
                    loading={loading}
                    initialState={{
                        sorting: {
                            sortModel: [{ field: "name", sort: "asc" }],
                        },
                    }}
                    rowSelectionModel={selectedWorkspace ? [selectedWorkspace.id] : []}
                    slotProps={{
                        toolbar: {
                            showQuickFilter: true,
                            printOptions: { disableToolbarButton: true }, // Hide Print
                            csvOptions: { disableToolbarButton: true }, // Hide Export
                        },
                        loadingOverlay: {
                            variant: "linear-progress",
                            noRowsVariant: "linear-progress",
                        },
                    }}
                />
            </Box>
            <FormControlLabel
                control={<Switch checked={errSwitch} onChange={() => setErrSwitch(!errSwitch)} />}
                label="Errors Only"
            />
        </div>
    );
}

export default function Workspaces() {
    const [selectedWorkspace, setSelectedWorkspace] = useState<DGWorkspaceRow>({
        id: "",
        name: "",
        owner: "",
        ok: true,
    });

    // Either show the spinner or the page content.
    return (
        <Grid container spacing={2}>
            <Grid size={3.5} alignItems="left" sx={{ display: "flex", flexDirection: "column" }}>
                {/* Show Groups Info box */}
                <WorkspaceInfoPaper selectedWorkspace={selectedWorkspace} />
                <Paper
                    sx={{
                        flexGrow: 1,
                        padding: 2,
                        display: "flex",
                        flexDirection: "column",
                    }}
                >
                    {/* Show list of Workspaces on the left.*/}
                    <WorkspaceGrid
                        selectedWorkspace={selectedWorkspace}
                        setSelectedWorkspace={setSelectedWorkspace}
                    />
                </Paper>
            </Grid>
            {/* Show all resources of selected Workspace. */}
            <Grid size={8.5} justifyContent="center" alignItems="center">
                <ResourceGrid selectedWorkspace={selectedWorkspace} />
            </Grid>
        </Grid>
    );
}
