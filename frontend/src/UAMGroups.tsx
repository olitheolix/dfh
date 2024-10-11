import React from "react";
import { useState, useEffect } from "react";
import {
    DataGrid,
    GridToolbar,
    GridEventListener,
    GridSortModel,
    GridRowSelectionModel,
} from "@mui/x-data-grid";
import {
    IconButton,
    CircularProgress,
    Button,
    Paper,
    Typography,
    Box,
    Dialog,
    DialogTitle,
    DialogContent,
    DialogActions,
    Autocomplete,
    TextField,
} from "@mui/material";
import { UAMUser, UAMGroup, DGUserRow, DGGroupRow } from "./UAMInterfaces";
import Grid from "@mui/material/Grid2";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import ArrowForwardIcon from "@mui/icons-material/ArrowForward";
import Title from "./Title";
import EditIcon from "@mui/icons-material/Edit";

const DataGridGroupColumns = [{ field: "name", headerName: "Name", flex: 1 }];
const DataGridUserColumns = [
    { field: "name", headerName: "Name", width: 150 },
    { field: "lanid", headerName: "LanID", width: 100 },
    { field: "email", headerName: "Email", flex: 1 },
];

// Show a paper with Group information.
export function GroupInfo({ selectedGroup }: { selectedGroup: UAMGroup }) {
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
                Group {selectedGroup.name}
                <IconButton size="small" aria-label="edit">
                    <EditIcon fontSize="small" />
                </IconButton>
            </Title>

            <Typography variant="subtitle1" gutterBottom>
                Owner: {selectedGroup.owner}
            </Typography>
            <Typography variant="subtitle1" gutterBottom>
                Provider: {selectedGroup.provider}
            </Typography>
        </Paper>
    );
}

function ShowAddGroup({
    isOpen,
    setIsOpen,
    setReloadGroups,
}: {
    isOpen: boolean;
    setIsOpen: React.Dispatch<React.SetStateAction<boolean>>;
    setReloadGroups: React.Dispatch<React.SetStateAction<boolean>>;
}) {
    const [options, setOptions] = useState<string[]>([]);
    const [groupOwner, setGroupOwner] = useState<string>("");
    const [groupName, setGroupName] = useState<string>("");

    useEffect(() => {
        // Fetch the list of all users when the dialog opens.
        if (isOpen) {
            fetch("/demo/api/uam/v1/users")
                .then((response) => response.json())
                .then((data) => {
                    const userList = data.map((user: UAMUser) => {
                        return user.name;
                    });
                    setOptions(userList);
                })
                .catch((error) =>
                    console.error("Error fetching users:", error),
                );
        }
    }, [isOpen]);

    const handleClose = () => {
        setIsOpen(false);
    };

    const handleOk = () => {
        if (groupOwner) {
            const payload: UAMGroup = {
                owner: groupOwner,
                name: groupName,
                provider: "",
                users: {},
                children: {},
            };

            fetch("/demo/api/uam/v1/groups", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload),
            })
                .then((response) => {
                    if (!response.ok) {
                        throw new Error(
                            `HTTP error! status: ${response.status}`,
                        );
                    }
                    setReloadGroups(true);
                })
                .catch((error) => console.error("Error adding user:", error));
        } else {
            console.warn("No user selected");
        }
        handleClose();
    };

    return (
        <Dialog open={isOpen} onClose={handleClose} fullWidth={true}>
            <DialogTitle>Group Owner</DialogTitle>
            <DialogContent>
                <Grid container spacing={2} alignItems="center">
                    <Grid size={10}>
                        <Autocomplete
                            options={options}
                            value={groupOwner}
                            onChange={(_, newValue) => {
                                setGroupOwner(newValue || "");
                            }}
                            renderInput={(params) => (
                                <TextField
                                    {...params}
                                    label="owner"
                                    variant="standard"
                                    fullWidth
                                />
                            )}
                        />
                    </Grid>
                    <Grid size={10}>
                        <TextField
                            label="group name"
                            type="string"
                            variant="standard"
                            onChange={(e) => setGroupName(e.target.value)}
                        />
                    </Grid>
                </Grid>
            </DialogContent>
            <DialogActions>
                <Button onClick={handleClose} color="primary">
                    Cancel
                </Button>
                <Button onClick={handleOk} color="primary" variant="contained">
                    OK
                </Button>
            </DialogActions>
        </Dialog>
    );
}

function removeDuplicateIds(data: any[]) {
    let seen: Set<string> = new Set();
    let out: any[] = [];

    for (const item of data) {
        if (seen.has(item.id)) continue;
        seen.add(item.id);
        out.push(item);
    }
    return out;
}

export default function UAMGroups() {
    const [loading, setLoading] = useState<boolean>(true);
    const [reloadGroups, setReloadGroups] = useState<boolean>(false);
    const [groupRows, setGroupRows] = useState<DGGroupRow[]>([]);
    const [leftUserRows, setLeftUserRows] = useState<DGUserRow[]>([]);
    const [rightUserRows, setRightUserRows] = useState<DGUserRow[]>([]);
    const [leftSelected, setLeftSelected] = useState<GridRowSelectionModel>([]);
    const [rightSelected, setRightSelected] = useState<GridRowSelectionModel>(
        [],
    );
    const [showAddGroup, setShowAddGroup] = useState<boolean>(false);
    const [selectedGroup, setSelectedGroup] = useState<DGGroupRow>({
        id: "",
        name: "",
        owner: "",
        provider: "",
        users: {},
        children: {},
    });

    const loadGroups = () => {
        fetch("/demo/api/uam/v1/groups")
            .then((response) => response.json())
            .then((jsonData) => {
                const data = jsonData.map((group: UAMGroup) => {
                    return { id: group.name, ...group } as DGGroupRow;
                });
                setGroupRows(data);
                setLoading(false);
                setReloadGroups(false);
            })
            .catch((error) => {
                console.error("Error fetching data:", error);
            });
    };

    // Populate the groups upon mounting the component.
    useEffect(() => {
        loadGroups();
    }, [reloadGroups]);

    // Notify the API whenever the content of the left changes, ie whenever
    // users were added/removed from the selected group.
    useEffect(() => {
        // Do nothing unless a group was selected. This special case occurs when
        // the component initially mounts and no record is selected in the
        // DataGrid of the groups yet.
        if (selectedGroup.id == "") return;

        // Set the users of the selected group based on the new content in the left grid.
        fetch(`/demo/api/uam/v1/groups/${selectedGroup.id}/users`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(leftUserRows.map((user) => user.email)),
        })
            .then((response) => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
            })
            .then(() => {
                console.log("User successfully added");
            })
            .catch((error) => console.error("Error adding user:", error));

        // Load all users in the system and remove those already displayed in
        // the left grid.
        fetch(`/demo/api/uam/v1/users`)
            .then((response) => response.json())
            .then((jsonData) => {
                // Compile set of IDs in left grid.
                const seen: Set<string> = new Set(
                    leftUserRows.map((user) => user.email),
                );

                // Compute all users not in the left grid.
                let users: DGUserRow[] = [];
                for (const user of jsonData) {
                    if (!seen.has(user.email)) {
                        const newRow: DGUserRow = { id: user.email, ...user };
                        users = [...users, newRow];
                    }
                }

                // Update the right grid.
                setRightUserRows(users);
                setLoading(false);
            })
            .catch((error) => {
                console.error("Error fetching data:", error);
            });
    }, [leftUserRows]);

    // When user clicks on a group we load all the users of that group into
    // the left list.
    const handleGroupRowClick: GridEventListener<"rowClick"> = (params) => {
        setSelectedGroup(params.row);
        fetch(`/demo/api/uam/v1/groups/${params.id}/users`)
            .then((response) => response.json())
            .then((jsonData) => {
                const rowData = jsonData.map((user: UAMUser) => {
                    return { id: user.email, ...user } as DGUserRow;
                });
                setLeftUserRows(rowData);
                setLoading(false);
            })
            .catch((error) => {
                console.error("Error fetching data:", error);
            });
    };

    const onMoveRightToLeft = () => {
        const itemsToMove = rightUserRows.filter((item) =>
            rightSelected.includes(item.id),
        );
        setLeftUserRows(removeDuplicateIds([...leftUserRows, ...itemsToMove]));
        setRightSelected([]);
    };

    const onMoveLeftToRight = () => {
        setLeftUserRows(
            leftUserRows.filter((item) => !leftSelected.includes(item.id)),
        );
        setLeftSelected([]);
    };

    const onSelectLeft = (selection: GridRowSelectionModel) => {
        setLeftSelected(selection);
    };
    const onSelectRight = (selection: GridRowSelectionModel) => {
        setRightSelected(selection);
    };
    const onOpenCreateGroupDialog = async () => {
        setShowAddGroup(true);
    };

    // Default sort model of the data grids.
    const sortModel = [{ field: "name", sort: "asc" }] as GridSortModel;

    // Either show the spinner or the page content.
    if (loading) {
        return (
            <Grid
                container
                justifyContent="center"
                alignItems="center"
                style={{ height: "100vh" }}
            >
                <Grid>
                    {" "}
                    <CircularProgress />{" "}
                </Grid>
            </Grid>
        );
    } else {
        return (
            <Grid container spacing={2}>
                <Grid size={3.5} alignItems="left">
                    <GroupInfo selectedGroup={selectedGroup as UAMGroup} />

                    {/* Show list of groups in the system */}
                    <Paper
                        style={{
                            padding: "20px",
                            display: "flex",
                            flexDirection: "column",
                        }}
                    >
                        <Title>Groups</Title>
                        <Box height="49.4vh">
                            <DataGrid
                                disableColumnSelector
                                rows={groupRows}
                                columns={DataGridGroupColumns}
                                slots={{ toolbar: GridToolbar }}
                                onRowClick={handleGroupRowClick}
                                keepNonExistentRowsSelected={false}
                                sortModel={sortModel}
                                slotProps={{
                                    toolbar: {
                                        showQuickFilter: true,
                                    },
                                }}
                            />
                        </Box>
                        <Button
                            variant="contained"
                            color="primary"
                            onClick={onOpenCreateGroupDialog}
                        >
                            Create Group
                        </Button>
                        <ShowAddGroup
                            isOpen={showAddGroup}
                            setIsOpen={setShowAddGroup}
                            setReloadGroups={setReloadGroups}
                        />
                    </Paper>
                </Grid>

                {/* Show users assigned to selected group. */}
                <Grid size={4} justifyContent="center" alignItems="center">
                    <Paper
                        style={{
                            padding: "20px",
                            display: "flex",
                            flexDirection: "column",
                        }}
                    >
                        <Title>Users in {selectedGroup.name}</Title>
                        <Box height="70vh">
                            <DataGrid
                                checkboxSelection
                                disableColumnSelector
                                rows={leftUserRows}
                                columns={DataGridUserColumns}
                                onRowSelectionModelChange={onSelectLeft}
                                keepNonExistentRowsSelected={false}
                                sortModel={sortModel}
                                slots={{ toolbar: GridToolbar }}
                                slotProps={{
                                    toolbar: {
                                        showQuickFilter: true,
                                    },
                                }}
                            />
                        </Box>
                    </Paper>
                </Grid>

                {/* Show left/right buttons to transfer users. */}
                <Grid
                    container
                    size={0.5}
                    justifyContent="center"
                    direction="column"
                >
                    <Button
                        variant="contained"
                        color="primary"
                        onClick={onMoveLeftToRight}
                    >
                        <ArrowForwardIcon />
                    </Button>
                    <Button
                        variant="contained"
                        color="primary"
                        onClick={onMoveRightToLeft}
                    >
                        <ArrowBackIcon />
                    </Button>
                </Grid>

                {/* Show available users. */}
                <Grid size={4} justifyContent="center" alignItems="center">
                    <Paper
                        style={{
                            padding: "20px",
                            display: "flex",
                            flexDirection: "column",
                        }}
                    >
                        <Title>Unassigned Users</Title>
                        <Box height="70vh">
                            <DataGrid
                                checkboxSelection
                                disableColumnSelector
                                rows={rightUserRows}
                                columns={DataGridUserColumns}
                                keepNonExistentRowsSelected={false}
                                onRowSelectionModelChange={onSelectRight}
                                sortModel={sortModel}
                                slots={{ toolbar: GridToolbar }}
                                slotProps={{
                                    toolbar: {
                                        showQuickFilter: true,
                                    },
                                }}
                            />
                        </Box>
                    </Paper>
                </Grid>
            </Grid>
        );
    }
}
