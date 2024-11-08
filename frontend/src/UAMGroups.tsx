import React from "react";
import Cookies from "js-cookie";
import { useState, useEffect, useContext } from "react";
import { DataGrid, GridEventListener, GridRowSelectionModel, GridToolbar } from "@mui/x-data-grid";
import {
    Autocomplete,
    Box,
    Button,
    CircularProgress,
    Dialog,
    DialogActions,
    DialogContent,
    DialogTitle,
    IconButton,
    List,
    Paper,
    TextField,
    Typography,
} from "@mui/material";
import { green, red } from "@mui/material/colors";
import { UAMUser, UAMGroup, DGUserRow, DGGroupRow } from "./UAMInterfaces";
import Grid from "@mui/material/Grid2";
import ArrowBackIcon from "@mui/icons-material/ArrowBack";
import ArrowForwardIcon from "@mui/icons-material/ArrowForward";
import Title from "./Title";
import EditIcon from "@mui/icons-material/Edit";
import { httpGet, httpPost, httpPut, HTTPErrorContext, HTTPErrorContextType } from "./WebRequests";

const DataGridGroupColumns = [
    { field: "name", headerName: "Name", flex: 1 },
    { field: "owner", headerName: "Owner", flex: 1 },
];
const DataGridUserColumns = [
    { field: "name", headerName: "Name", width: 200 },
    { field: "slack", headerName: "Slack", width: 100 },
    { field: "lanid", headerName: "LanID", width: 100 },
    { field: "email", headerName: "Email", width: 200 },
    { field: "role", headerName: "Role", width: 100 },
    { field: "manager", headerName: "Manager", flex: 1 },
];

// Show a paper with Group information.
export function GroupInfo({
    selectedGroup,
    setSelectedGroup,
    setReloadGroups,
    errCtx,
}: {
    selectedGroup: DGGroupRow;
    setSelectedGroup: React.Dispatch<React.SetStateAction<DGGroupRow>>;
    setReloadGroups: React.Dispatch<React.SetStateAction<boolean>>;
    errCtx: HTTPErrorContextType;
}) {
    const [showAddGroup, setShowAddGroup] = useState<boolean>(false);

    const openEditDialog = () => {
        setShowAddGroup(true);
    };

    return (
        <Paper
            style={{
                padding: "20px",
                display: "flex",
                flexDirection: "column",
            }}
            sx={{ mt: 0, mb: 6 }}
        >
            <AddOrModifyGroupDialog
                isOpen={showAddGroup}
                setIsOpen={setShowAddGroup}
                isGroupCreate={false}
                setReloadGroups={setReloadGroups}
                selectedGroup={selectedGroup}
                setSelectedGroup={setSelectedGroup}
                errCtx={errCtx}
            />

            <Title>
                <Box display="flex" justifyContent="space-between" alignItems="center">
                    Group {selectedGroup.name}
                    <IconButton
                        size="small"
                        aria-label="edit"
                        onClick={openEditDialog}
                        disabled={selectedGroup.name == ""}
                    >
                        <EditIcon fontSize="small" />
                    </IconButton>
                </Box>
            </Title>

            <Typography variant="subtitle1" gutterBottom>
                Owner: {selectedGroup.owner}
            </Typography>
            <Typography variant="subtitle1" gutterBottom>
                Provider: {selectedGroup.provider}
            </Typography>
            <Typography variant="subtitle1" gutterBottom>
                Description: {selectedGroup.description}
            </Typography>
        </Paper>
    );
}

export function AddOrModifyGroupDialog({
    isOpen,
    setIsOpen,
    isGroupCreate,
    setReloadGroups,
    selectedGroup,
    setSelectedGroup,
    errCtx,
}: {
    isOpen: boolean;
    setIsOpen: React.Dispatch<React.SetStateAction<boolean>>;
    isGroupCreate: boolean;
    setReloadGroups: React.Dispatch<React.SetStateAction<boolean>>;
    selectedGroup: DGGroupRow;
    setSelectedGroup: React.Dispatch<React.SetStateAction<DGGroupRow>>;
    errCtx: HTTPErrorContextType;
}) {
    const [options, setOptions] = useState<string[]>([]);
    const [groupOwner, setGroupOwner] = useState<string>(selectedGroup.owner);
    const [groupName, setGroupName] = useState<string>(selectedGroup.name);
    const [groupDescription, setGroupDescription] = useState<string>(selectedGroup.description);

    useEffect(() => {
        setGroupOwner(selectedGroup.owner);
        setGroupName(selectedGroup.name);

        const loadAllUsers = async () => {
            if (isOpen) {
                const ret = await httpGet("/demo/api/uam/v1/users");
                if (ret.err) {
                    errCtx.showError(ret.err);
                    return;
                }
                const userList = ret.data.map((user: UAMUser) => {
                    return user.email;
                });
                setOptions(userList);

                // Pre-select the current user in the AutoComplete component.
                setGroupOwner(currentOwner(userList));
            }
        };

        loadAllUsers();
    }, [isOpen]);

    const handleClose = () => {
        setIsOpen(false);
    };

    const onCreateGroup = async () => {
        const payload: UAMGroup = {
            owner: groupOwner,
            name: groupName,
            description: groupDescription,
            provider: "",
            users: [],
            children: [],
            roles: [],
        };

        const method = isCreate() ? httpPost : httpPut;
        const ret = await method("/demo/api/uam/v1/groups", {
            body: JSON.stringify(payload),
        });

        // Update the selectedGroup prop to ensure the GroupInfo panel re-renders itself.
        if (!isCreate()) {
            setSelectedGroup({ id: payload.name, ...payload });
        }
        setReloadGroups(true);
        handleClose();
        if (ret.err) {
            errCtx.showError(ret.err);
            return;
        }
    };

    // Return `true` if this dialog was opened to create a group and `false` if it
    // was opened to modify an existing group.
    const isCreate = () => {
        return isGroupCreate == true;
    };

    const getTitle = () => {
        return isCreate() ? "Create Group" : "Modify Group";
    };

    // Return the owner of the selected group (modify mode) or the currently
    // logged in user if it exists in the system.
    const currentOwner = (users: string[]): string => {
        if (!isCreate()) return selectedGroup.owner;
        const email = Cookies.get("email") || "";
        return users.includes(email) ? email : "";
    };

    return (
        <Dialog open={isOpen} onClose={handleClose} fullWidth={true} disableRestoreFocus>
            <DialogTitle>{getTitle()}</DialogTitle>
            <DialogContent>
                <Grid container spacing={2} alignItems="center">
                    <Grid size={10}>
                        <TextField
                            label="name"
                            type="string"
                            autoFocus
                            variant="standard"
                            {...(isCreate()
                                ? { defaultValue: "" }
                                : { value: selectedGroup.name, disabled: true })}
                            onChange={(e) => setGroupName(e.target.value)}
                        />
                    </Grid>
                    <Grid size={10}>
                        <Autocomplete
                            options={options}
                            value={groupOwner}
                            onChange={(_, newValue) => {
                                setGroupOwner(newValue || "");
                            }}
                            inputValue={groupOwner}
                            onInputChange={(_event, newInputValue) => {
                                setGroupOwner(newInputValue);
                            }}
                            renderInput={(params) => (
                                <TextField {...params} label="owner" variant="standard" fullWidth />
                            )}
                        />
                    </Grid>
                    <TextField
                        label="description"
                        type="string"
                        variant="standard"
                        defaultValue={selectedGroup.description}
                        onChange={(e) => setGroupDescription(e.target.value)}
                    />
                </Grid>
            </DialogContent>
            <DialogActions>
                <Button onClick={handleClose} color="primary">
                    Cancel
                </Button>
                <Button
                    onClick={onCreateGroup}
                    color="primary"
                    variant="contained"
                    disabled={groupOwner === "" || groupName === ""}
                >
                    {isCreate() ? "Create" : "Update"}
                </Button>
            </DialogActions>
        </Dialog>
    );
}

export function ModifyUsersDialog({
    isOpen,
    setIsOpen,
    selectedGroup,
    leftUserRows,
    setLeftUserRows,
    errCtx,
}: {
    isOpen: boolean;
    setIsOpen: React.Dispatch<React.SetStateAction<boolean>>;
    selectedGroup: DGGroupRow;
    leftUserRows: DGUserRow[];
    setLeftUserRows: React.Dispatch<React.SetStateAction<DGUserRow[]>>;
    errCtx: HTTPErrorContextType;
}) {
    const [addedRows, setAddedRows] = useState<DGUserRow[]>([]);
    const [allUsers, setAllUsers] = useState<DGUserRow[]>([]);
    const [initialRows, setInitialRows] = useState<DGUserRow[]>([]);
    const [leftSelected, setLeftSelected] = useState<GridRowSelectionModel>([]);
    const [loading, setLoading] = useState<boolean>(true);
    const [removedRows, setRemovedRows] = useState<DGUserRow[]>([]);
    const [rightSelected, setRightSelected] = useState<GridRowSelectionModel>([]);
    const [rightUserRows, setRightUserRows] = useState<DGUserRow[]>([]);
    const [rowsDict, setRowsDict] = useState<RowsDict>({});
    const [showConfirmation, setShowConfirmation] = useState<boolean>(false);

    type DictValue = {
        isLeft: boolean;
        row: DGUserRow;
    };
    type RowsDict = {
        [key: string]: DictValue; // Key is a string and value is of type DictValue
    };

    useEffect(() => {
        // Backup the initial state so that we can compute a diff.
        setInitialRows(leftUserRows);

        // Load all users and compile them into a dict.
        loadAllUsers();
        const db: RowsDict = {};
        for (const user of allUsers) {
            db[user.email] = { isLeft: false, row: user };
            db[user.email].row.id = user.email;
        }

        // Iterate over all the users in the original group and change their
        // `isLeft` flag to true. We will use this flag to nominate the
        // left/right DataGrid.
        for (const row of leftUserRows) {
            db[row.id] = { isLeft: true, row };
        }

        setRowsDict(db);
    }, [isOpen]);

    useEffect(() => {
        // Iterate over our mini DB and compile the list of rows that go into
        // the left/right DataGrid.
        const right = Object.values(rowsDict)
            .filter((item) => !item.isLeft)
            .map((item) => item.row);
        const left = Object.values(rowsDict)
            .filter((item) => item.isLeft)
            .map((item) => item.row);

        setLeftUserRows(left);
        setRightUserRows(right);
    }, [rowsDict]);

    const loadAllUsers = async () => {
        setLoading(true);
        const ret = await httpGet("/demo/api/uam/v1/users");
        setLoading(false);

        if (ret.err) {
            errCtx.showError(ret.err);
            return;
        }

        setAllUsers(ret.data as DGUserRow[]);
    };

    // Determine the set of users that have been added or removed since mounting
    // the component.
    const computeDiff = () => {
        const old = new Set(initialRows.map((user) => user.id));
        const now = new Set(leftUserRows.map((user) => user.id));

        const added = leftUserRows.filter((user) => !old.has(user.id));
        const removed = initialRows.filter((user) => !now.has(user.id));

        setAddedRows(added);
        setRemovedRows(removed);
    };

    const closeDialog = () => {
        if (showConfirmation) {
            setShowConfirmation(false);
        } else {
            setIsOpen(false);
        }
    };

    const onApply = async () => {
        if (showConfirmation) {
            let ret = await httpPut(`/demo/api/uam/v1/groups/${selectedGroup.name}/users`, {
                body: JSON.stringify(leftUserRows.map((user) => user.email)),
            });
            setShowConfirmation(false);
            setIsOpen(false);
            if (ret.err) {
                errCtx.showError(ret.err);
                return;
            }
        } else {
            computeDiff();
            setShowConfirmation(true);
        }
    };

    const onMoveRightToLeft = () => {
        const updatedRowsDict = { ...rowsDict };
        for (const sel of rightSelected as string[]) {
            updatedRowsDict[sel] = { ...updatedRowsDict[sel], isLeft: true };
        }
        setRightSelected([]);
        setRowsDict(updatedRowsDict);
    };

    const onMoveLeftToRight = () => {
        const updatedRowsDict = { ...rowsDict };
        for (const sel of leftSelected as string[]) {
            updatedRowsDict[sel] = { ...updatedRowsDict[sel], isLeft: false };
        }
        setLeftSelected([]);
        setRowsDict(updatedRowsDict);
    };

    const onSelectLeft = (selection: GridRowSelectionModel) => {
        setLeftSelected(selection);
    };
    const onSelectRight = (selection: GridRowSelectionModel) => {
        setRightSelected(selection);
    };

    const renderSpinner = () => {
        return (
            <Grid container justifyContent="center" alignItems="center">
                <Grid>
                    <CircularProgress />
                </Grid>
            </Grid>
        );
    };

    const renderDiff = () => (
        <List>
            {addedRows.map((row) => (
                <Typography
                    key={row.id}
                    sx={{
                        color: green[500],
                        whiteSpace: "pre-wrap",
                        fontFamily: "monospace",
                    }}
                >
                    {`+ ${row.email}`}
                </Typography>
            ))}
            {removedRows.map((row) => (
                <Typography
                    key={row.id}
                    sx={{
                        color: red[500],
                        whiteSpace: "pre-wrap",
                        fontFamily: "monospace",
                    }}
                >
                    {`- ${row.email}`}
                </Typography>
            ))}
        </List>
    );

    const DataGridUserColumns = [
        { field: "name", headerName: "Name", width: 150 },
        { field: "lanid", headerName: "LanID", width: 75 },
        { field: "email", headerName: "Email", width: 150 },
        { field: "manager", headerName: "Manager", flex: 1 },
    ];

    const renderMainDialog = () => {
        return (
            <>
                <DialogTitle>Members of {selectedGroup.name}</DialogTitle>
                <Grid
                    container
                    spacing={2}
                    padding={5}
                    style={{ height: "100%" }}
                    justifyContent="space-between"
                >
                    {/* Left column with DataGrid */}
                    <Grid
                        size={5.5}
                        style={{
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "center",
                            flexDirection: "column",
                        }}
                    >
                        <Box style={{ height: "100%", width: "100%" }}>
                            <Title>Members</Title>
                            <DataGrid
                                checkboxSelection
                                disableColumnSelector
                                rows={leftUserRows}
                                columns={DataGridUserColumns}
                                rowSelectionModel={leftSelected}
                                onRowSelectionModelChange={onSelectLeft}
                                keepNonExistentRowsSelected={false}
                                slots={{ toolbar: GridToolbar }}
                                initialState={{
                                    sorting: {
                                        sortModel: [{ field: "name", sort: "asc" }],
                                    },
                                }}
                                slotProps={{
                                    toolbar: {
                                        showQuickFilter: true,
                                    },
                                }}
                                style={{ height: "72vh" }}
                            />
                        </Box>
                    </Grid>

                    {/* Middle column with Button */}
                    <Grid
                        style={{
                            display: "flex",
                            justifyContent: "center",
                            alignItems: "center",
                        }}
                    >
                        {/* Show left/right buttons to transfer users. */}
                        <Box
                            display="flex"
                            flexDirection="column"
                            alignItems="center"
                            justifyContent="center"
                        >
                            <Button
                                variant="contained"
                                color="primary"
                                onClick={onMoveLeftToRight}
                                sx={{ mb: 2 }}
                            >
                                <ArrowForwardIcon />
                            </Button>
                            <Button variant="contained" color="primary" onClick={onMoveRightToLeft}>
                                <ArrowBackIcon />
                            </Button>
                        </Box>
                    </Grid>

                    {/* Right column with DataGrid */}
                    <Grid size={5.5} style={{ display: "flex", flexDirection: "column" }}>
                        <Box style={{ height: "100%", width: "100%" }}>
                            <Title>Unassigned Users</Title>
                            <DataGrid
                                checkboxSelection
                                disableColumnSelector
                                rows={rightUserRows}
                                columns={DataGridUserColumns}
                                keepNonExistentRowsSelected={false}
                                rowSelectionModel={rightSelected}
                                onRowSelectionModelChange={onSelectRight}
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
                                style={{ height: "72vh" }}
                            />
                        </Box>
                    </Grid>
                </Grid>
            </>
        );
    };

    const renderConfirmationDialog = () => {
        return (
            <>
                <DialogTitle>Proposed Changes to {selectedGroup.name}</DialogTitle>
                <DialogContent sx={{ display: "flex", flexDirection: "column" }}>
                    {/* Show users assigned to selected group. */}
                    {renderDiff()}
                </DialogContent>
            </>
        );
    };

    return (
        <Dialog open={isOpen} onClose={closeDialog} fullWidth={true} maxWidth="xl">
            {showConfirmation ? renderConfirmationDialog() : renderMainDialog()}
            {loading ? renderSpinner() : null}
            <DialogActions>
                <Button onClick={closeDialog} color="primary">
                    Cancel
                </Button>
                <Button onClick={onApply} color="primary" variant="contained">
                    Apply
                </Button>
            </DialogActions>
        </Dialog>
    );
}

export default function UAMGroups() {
    const [loading, setLoading] = useState<boolean>(true);
    const [reloadGroups, setReloadGroups] = useState<boolean>(true);
    const [groupRows, setGroupRows] = useState<DGGroupRow[]>([]);
    const [leftUserRows, setLeftUserRows] = useState<DGUserRow[]>([]);
    const [showAddGroup, setShowAddGroup] = useState<boolean>(false);
    const [showModifyUsers, setShowModifyUsers] = useState<boolean>(false);
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

    const loadGroups = async () => {
        const ret = await httpGet("/demo/api/uam/v1/groups");
        setLoading(false);

        if (ret.err) {
            errCtx.showError(ret.err);
            return;
        }

        const data = ret.data.map((group: UAMGroup) => {
            return { id: group.name, ...group } as DGGroupRow;
        });
        setGroupRows(data);
    };

    // Populate the groups upon mounting the component.
    useEffect(() => {
        if (!reloadGroups) return;
        setReloadGroups(false);
        loadGroups();
    }, [reloadGroups]);

    // When user clicks on a group we load all the users of that group into
    // the left list.
    const handleGroupRowClick: GridEventListener<"rowClick"> = async (params) => {
        setSelectedGroup(params.row);

        const ret = await httpGet(`/demo/api/uam/v1/groups/${params.row.name}/users`);
        if (ret.err) {
            errCtx.showError(ret.err);
            return;
        }
        const rowData = ret.data.map((user: UAMUser) => {
            return { id: user.email, ...user } as DGUserRow;
        });
        setLeftUserRows(rowData);
        setLoading(false);
    };

    const onOpenCreateGroupDialog = async () => {
        setShowAddGroup(true);
    };

    const onOpenModifyUsersDialog = async () => {
        setShowModifyUsers(true);
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
                <AddOrModifyGroupDialog
                    isOpen={showAddGroup}
                    setIsOpen={setShowAddGroup}
                    isGroupCreate={true}
                    setReloadGroups={setReloadGroups}
                    selectedGroup={selectedGroup}
                    setSelectedGroup={setSelectedGroup}
                    errCtx={errCtx}
                />

                <ModifyUsersDialog
                    isOpen={showModifyUsers}
                    setIsOpen={setShowModifyUsers}
                    selectedGroup={selectedGroup}
                    leftUserRows={leftUserRows}
                    setLeftUserRows={setLeftUserRows}
                    errCtx={errCtx}
                />

                <Grid size={3.5} alignItems="left">
                    {/* Show Groups Info box */}
                    <GroupInfo
                        selectedGroup={selectedGroup}
                        setSelectedGroup={setSelectedGroup}
                        setReloadGroups={setReloadGroups}
                        errCtx={errCtx}
                    />

                    {/* Show list of groups in the system with a button to create new ones at the bottom.*/}
                    <Paper
                        style={{
                            padding: "20px",
                            display: "flex",
                            flexDirection: "column",
                        }}
                    >
                        <Title>Groups</Title>
                        <Box height="46.5vh">
                            <DataGrid
                                disableColumnSelector
                                rows={groupRows}
                                columns={DataGridGroupColumns}
                                slots={{ toolbar: GridToolbar }}
                                onRowClick={handleGroupRowClick}
                                keepNonExistentRowsSelected={false}
                                initialState={{
                                    sorting: {
                                        sortModel: [{ field: "name", sort: "asc" }],
                                    },
                                }}
                                rowSelectionModel={selectedGroup ? [selectedGroup.id] : []}
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
                    </Paper>
                </Grid>
                {/* Show users assigned to selected group. */}
                <Grid size={8.5} justifyContent="center" alignItems="center">
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
                                disableColumnSelector
                                rows={leftUserRows}
                                columns={DataGridUserColumns}
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
                        </Box>
                        <Button
                            variant="contained"
                            color="primary"
                            onClick={onOpenModifyUsersDialog}
                            disabled={selectedGroup.name == "" ? true : false}
                        >
                            Modify Members
                        </Button>
                    </Paper>
                </Grid>
            </Grid>
        );
    }
}
