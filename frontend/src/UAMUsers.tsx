import React from "react";
import { useState, useEffect, useContext } from "react";
import { DataGrid, GridEventListener, GridToolbar, GridColDef } from "@mui/x-data-grid";
import { Box, CircularProgress, Paper } from "@mui/material";
import { UAMUser, DGUserRow, DGGroupRow, DGUserRolesRow } from "./UAMInterfaces";
import Grid from "@mui/material/Grid2";
import Title from "./Title";
import { httpGet, HTTPErrorContext, HTTPErrorContextType } from "./WebRequests";

const RoleGridGroupColumns: GridColDef[] = [
    { field: "role", headerName: "Role", width: 400 },
    {
        field: "sources",
        headerName: "Sources",
        width: 300,
        flex: 1,
        renderCell: (params) => (
            <>
                {params.value.map((group: string, _index: number) => (
                    <Box key={_index} style={{ marginBottom: 10 }}>
                        {group}
                    </Box>
                ))}
            </>
        ),
    },
];

const DataGridUserColumns = [
    { field: "name", headerName: "Name", width: 200 },
    { field: "slack", headerName: "Slack", width: 100 },
    { field: "lanid", headerName: "LanID", width: 100 },
    { field: "email", headerName: "Email", width: 200 },
    { field: "role", headerName: "Role", width: 100 },
    { field: "manager", headerName: "Manager", flex: 1 },
];

export default function UAMUsers() {
    const [loading, setLoading] = useState<boolean>(true);
    const [roleRows, setRoleRows] = useState<DGUserRolesRow[]>([]);
    const [userRows, setUserRows] = useState<DGUserRow[]>([]);
    const [selectedGroup, setSelectedGroup] = useState<DGGroupRow>({
        id: "",
        name: "",
        owner: "",
        provider: "",
        description: "",
        users: [],
        children: [],
        roles: [],
    });
    const [errCtx, _] = React.useState<HTTPErrorContextType>(useContext(HTTPErrorContext));

    const loadUsers = async () => {
        const ret = await httpGet("/demo/api/uam/v1/users");
        setLoading(false);

        if (ret.err) {
            errCtx.showError(ret.err);
            return;
        }

        const data = ret.data.map((user: UAMUser) => {
            return { id: user.email, ...user } as DGUserRow;
        });
        setUserRows(data);
    };

    // Populate the users upon mounting the component.
    useEffect(() => {
        loadUsers();
    }, []);

    // Populate the roles of the clicked user.
    const handleUserRowClick: GridEventListener<"rowClick"> = async (params) => {
        setSelectedGroup(params.row);

        const ret = await httpGet(`/demo/api/uam/v1/users/${params.row.email}/roles`);
        if (ret.err) {
            errCtx.showError(ret.err);
            return;
        }
        const tmpMap = new Map<string, string[]>(Object.entries(ret.data.inherited));
        const rolesData = Array.from(tmpMap, ([key, value]) => ({
            id: key,
            role: key,
            sources: value,
        }));

        setRoleRows(rolesData);
        setLoading(false);
    };

    // Either show the spinner or the page content.
    if (loading) {
        return (
            <Grid container justifyContent="center" alignItems="center" style={{ height: "100vh" }}>
                <Grid>
                    {" "}
                    <CircularProgress />{" "}
                </Grid>
            </Grid>
        );
    } else {
        return (
            <Grid container spacing={2}>
                {/* Show users assigned to selected group. */}
                <Grid size={7} justifyContent="center" alignItems="center">
                    <Box height="80vh">
                        <Paper
                            style={{
                                padding: "20px",
                                display: "flex",
                                flexDirection: "column",
                                height: "100%",
                            }}
                        >
                            <Title>Users</Title>
                            <DataGrid
                                disableColumnSelector
                                rows={userRows}
                                columns={DataGridUserColumns}
                                onRowClick={handleUserRowClick}
                                keepNonExistentRowsSelected={false}
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
                                }}
                            />
                        </Paper>
                    </Box>
                </Grid>
                <Grid size={5} alignItems="left">
                    {/* Show the inherited group roles.*/}
                    <Box style={{ height: "80vh" }}>
                        <Paper
                            style={{
                                padding: "20px",
                                display: "flex",
                                flexDirection: "column",
                                height: "100%",
                            }}
                        >
                            <Title>Inherited Roles</Title>
                            <DataGrid
                                disableColumnSelector
                                rows={roleRows}
                                columns={RoleGridGroupColumns}
                                slots={{ toolbar: GridToolbar }}
                                keepNonExistentRowsSelected={false}
                                rowSelectionModel={selectedGroup ? [selectedGroup.id] : []}
                                getRowHeight={() => "auto"}
                                initialState={{
                                    sorting: {
                                        sortModel: [{ field: "role", sort: "asc" }],
                                    },
                                }}
                                slotProps={{
                                    toolbar: {
                                        showQuickFilter: true,
                                    },
                                }}
                            />
                        </Paper>
                    </Box>
                </Grid>
            </Grid>
        );
    }
}
