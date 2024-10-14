import React from 'react';
import { useState, useEffect } from 'react';
import { DataGrid, GridToolbar, GridEventListener, GridColDef, GridSortModel, GridRowSelectionModel } from '@mui/x-data-grid';
import { CircularProgress, Button, Paper, Typography, Box, Dialog, DialogTitle, DialogContent, DialogActions, Autocomplete, TextField } from '@mui/material';
import { UAMUser, UAMGroup, POSTGroup, POSTGroupMembers } from './UAMInterfaces'
import Grid from '@mui/material/Grid2';
import ArrowBackIcon from '@mui/icons-material/ArrowBack';
import ArrowForwardIcon from '@mui/icons-material/ArrowForward';

import Title from './Title';

const DataGridGroupColumns = [
    { field: 'name', headerName: 'Name', flex: 1 },
]
const DataGridUserColumns = [
    { field: 'name', headerName: 'Name', width: 150 },
    { field: 'lanid', headerName: 'LanID', width: 100 },
    { field: 'email', headerName: 'Email', flex: 1 },
]


function ShowAddGroup({ isOpen, setIsOpen }: { isOpen: boolean, setIsOpen: React.Dispatch<React.SetStateAction<boolean>> }) {
    const [options, setOptions] = useState<string[]>([]);
    const [groupOwner, setGroupOwner] = useState<string>("");
    const [groupName, setGroupName] = useState<string>("");

    useEffect(() => {
        // Fetch the list of users from the /users endpoint when the dialog opens
        if (isOpen) {
            fetch('/demo/api/users')
                .then(response => response.json())
                .then(data => {
                    const userList = data.map((row: UAMUser) => {
                        return row.name
                    })
                    setOptions(userList);
                })
                .catch(error => console.error('Error fetching users:', error));
        }
    }, [isOpen]);

    const handleClose = () => {
        setIsOpen(false);
    };

    const handleOk = () => {
        if (groupOwner) {
            const payload: POSTGroup = {
                ownerId: groupOwner, name: groupName,
                provider: ""
            }

            fetch('/demo/api/groups', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(payload),
            })
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    }
                    return response.json();
                })
                .then(() => {
                    console.log('User successfully added');
                })
                .catch(error => console.error('Error adding user:', error));
        } else {
            console.warn('No user selected');
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
                            onChange={(_, newValue) => { setGroupOwner(newValue || ""); }}
                            renderInput={(params) => (
                                <TextField {...params} label="owner" variant="standard" fullWidth />
                            )}
                        />
                    </Grid>
                    <Grid size={10}>
                        <TextField label="group name" type="string" variant="standard"
                            onChange={(e) => setGroupName(e.target.value)} />
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
};

interface DGUserRow {
    id: string
    name: string
    owner: string
    provider: string
}


export default function UAMGroups() {
    const [loading, setLoading] = useState<boolean>(true);
    const [groupColumns, setGroupColumns] = useState<GridColDef[]>(DataGridGroupColumns);
    const [userColumns, setUserColumns] = useState<GridColDef[]>(DataGridUserColumns);
    const [groupRows, setGroupRows] = useState<any[]>([]);
    const [leftUserRows, setLeftUserRows] = useState<any[]>([]);
    const [rightUserRows, setRightUserRows] = useState<any[]>([]);
    const [selectedGroup, setSelectedGroup] = useState<DGUserRow>({
        id: "",
        name: "",
        owner: "",
        provider: "",
    });
    const [leftSelected, setLeftSelected] = useState<GridRowSelectionModel>([]);
    const [rightSelected, setRightSelected] = useState<GridRowSelectionModel>([]);
    const [sortModel, setSortModel] = React.useState<GridSortModel>([{ field: "name", sort: "asc" }]);
    const [showAddGroup, setShowAddGroup] = useState<boolean>(false);

    useEffect(() => {
        fetch('/demo/api/groups')
            .then(response => response.json())
            .then(jsonData => {
                const data = jsonData.map((row: UAMGroup) => {
                    return {
                        name: row.name,
                        owner: row.owner,
                        provider: row.provider,
                        id: row.uid,
                    }
                })
                setGroupRows(data)
                setLoading(false);
            })
            .catch(error => {
                console.error('Error fetching data:', error);
            });
    }, []);

    // Notify the API whenever the content of the left (ie selected group) changes.
    useEffect(() => {
        let payload: POSTGroupMembers = {
            groupId: selectedGroup.id,
            userIds: leftUserRows.map(row => row.id),
        }

        // Only call the API if a group was actually selected. We need to
        // intercept this case because the DataGrid does not have a row selected initially.
        if (payload.groupId != '') {
            fetch('/demo/api/groups/members', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify(payload),
            })
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    }
                    return response.json();
                })
                .then(() => {
                    console.log('User successfully added');
                })
                .catch(error => console.error('Error adding user:', error));

            fetch(`/demo/api/users`)
                .then(response => response.json())
                .then(jsonData => {
                    const data: DGUserRow[] = jsonData.map((row: UAMUser) => {
                        return {
                            name: row.name,
                            email: row.email,
                            slack: row.slack,
                            lanid: row.lanid,
                            id: row.uid,
                        }
                    })
                    // Remove all entries from right that already exist in left.
                    let right_dict = data.reduce<Record<string, any>>((acc, item) => {
                        acc[item.id] = item;
                        return acc;
                    }, {});
                    for (const row of leftUserRows) {
                        delete right_dict[row.id]
                    }
                    setRightUserRows(Object.values(right_dict))
                    setLoading(false);
                })
                .catch(error => {
                    console.error('Error fetching data:', error);
                });
        }
    }, [leftUserRows]);


    if (loading) {
        return <CircularProgress />;
    }

    const onOpenCreateGroupDialog = async () => {
        setShowAddGroup(true)
    }

    const handleGroupRowClick: GridEventListener<'rowClick'> = (params) => {
        setSelectedGroup(params.row)
        fetch(`/demo/api/users/${params.id}`)
            .then(response => response.json())
            .then(jsonData => {
                const data = jsonData.map((row: UAMUser) => {
                    return {
                        name: row.name,
                        email: row.email,
                        slack: row.slack,
                        lanid: row.lanid,
                        id: row.uid,
                    }
                })
                setLeftUserRows(data)
                setLoading(false);
            })
            .catch(error => {
                console.error('Error fetching data:', error);
            });
    };

    const onSelectLeft = (selection: GridRowSelectionModel) => { setLeftSelected(selection); };
    const onSelectRight = (selection: GridRowSelectionModel) => { setRightSelected(selection); };

    const onMoveRightToLeft = () => {
        const itemsToMove = rightUserRows.filter((item) => rightSelected.includes(item.id));

        // Merge the rows and remove duplicates.
        let merged = [...leftUserRows, ...itemsToMove]
        let merged_dict = merged.reduce<Record<string, any>>((acc, item) => {
            acc[item.id] = item;
            return acc;
        }, {});
        const merged_unique = Object.values(merged_dict)

        setLeftUserRows(merged_unique);
        setRightSelected([]);
    }

    const onMoveLeftToRight = () => {
        setLeftUserRows(leftUserRows.filter((item) => !leftSelected.includes(item.id)));
        setLeftSelected([]);
    };

    return (
        <Grid container spacing={2}>
            <Grid size={3.5} alignItems="left">
                {/* Info Field */}
                <Paper style={{
                    padding: '20px', display: 'flex',
                    flexDirection: 'column',
                }} sx={{ mt: 0, mb: 6 }}>
                    <Title>Group {selectedGroup.name}</Title>

                    <Grid container size="grow" spacing={2}>
                        <Grid>
                            <Typography variant="subtitle1" gutterBottom>
                                Owner: {selectedGroup.owner}
                            </Typography>
                        </Grid>
                        <Grid>
                            <Typography variant="subtitle1" gutterBottom>
                                Provider: {selectedGroup.provider}
                            </Typography>
                        </Grid>
                    </Grid>
                </Paper>

                <Paper style={{ padding: '20px', display: 'flex', flexDirection: 'column', }}>
                    <Title>Groups</Title>
                    <Box height="49.4vh">
                        <DataGrid
                            disableColumnSelector
                            rows={groupRows}
                            columns={groupColumns}
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
                    </Box >
                    <Button variant="contained" color="primary" onClick={onOpenCreateGroupDialog}>Create Group</Button>
                    <ShowAddGroup isOpen={showAddGroup} setIsOpen={setShowAddGroup} />
                </Paper>
            </Grid>
            <Grid size={4} justifyContent="center" alignItems="center">
                <Paper style={{ padding: '20px', display: 'flex', flexDirection: 'column', }}>
                    <Title>Users in {selectedGroup.name}</Title>
                    <Box height="70vh">
                        <DataGrid
                            checkboxSelection
                            disableColumnSelector
                            rows={leftUserRows}
                            columns={userColumns}
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
                    </Box >
                </Paper>
            </Grid>
            <Grid container size={0.5} justifyContent="center" direction="column">
                <Button variant="contained" color="primary" onClick={onMoveLeftToRight}><ArrowForwardIcon /></Button>
                <Button variant="contained" color="primary" onClick={onMoveRightToLeft}><ArrowBackIcon /></Button>
            </Grid>
            <Grid size={4} justifyContent="center" alignItems="center">
                <Paper style={{ padding: '20px', display: 'flex', flexDirection: 'column', }}>
                    <Title>Unassigned Users</Title>
                    <Box height="70vh">
                        <DataGrid
                            checkboxSelection
                            disableColumnSelector
                            rows={rightUserRows}
                            columns={userColumns}
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
                    </Box >
                </Paper>
            </Grid>

        </Grid >
    );
};
