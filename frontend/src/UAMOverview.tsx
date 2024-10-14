import React from 'react';
import { useState, useEffect } from 'react';
import Box from '@mui/material/Box';
import { SimpleTreeView } from '@mui/x-tree-view/SimpleTreeView';
import { TreeItem } from '@mui/x-tree-view/TreeItem';
import Grid from '@mui/material/Grid2';
import { DataGrid } from '@mui/x-data-grid';
import { GridColDef } from '@mui/x-data-grid';
import { CircularProgress, Button } from '@mui/material';
import { GridToolbar } from '@mui/x-data-grid';
import {
    Paper, Typography, Dialog, DialogTitle, DialogContent, DialogActions,
    Autocomplete, TextField,
} from '@mui/material';

import Title from './Title';
import { UAMUser, UAMGroup } from './UAMInterfaces'


function ShowAddUser({ isOpen, setIsOpen }: { isOpen: boolean, setIsOpen: React.Dispatch<React.SetStateAction<boolean>> }) {
    const [options, setOptions] = useState<string[]>([]);
    const [selectedUser, setSelectedUser] = useState<string | null>(null);

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
        if (selectedUser) {
            fetch('/users', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ user: selectedUser }),
            })
                .then(response => {
                    if (!response.ok) {
                        throw new Error(`HTTP error! status: ${response.status}`);
                    }
                    return response.json();
                })
                .then(() => {
                    console.log('User successfully added');
                    handleClose();
                })
                .catch(error => console.error('Error adding user:', error));
        } else {
            console.warn('No user selected');
        }
    };

    return (
        <Dialog open={isOpen} onClose={handleClose} fullWidth={true}>
            <DialogTitle>Select a User</DialogTitle>
            <DialogContent>
                <Autocomplete
                    options={options}
                    value={selectedUser}
                    onChange={(_, newValue) => { setSelectedUser(newValue); }}
                    renderInput={(params) => (
                        <TextField {...params} label="User" variant="outlined" fullWidth />
                    )}
                />
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


export default function UAMOverview() {
    const [treeData, setTreeData] = useState<UAMGroup>({
        uid: "n/a",
        name: "n/a",
        users: [],
        children: [],
    });
    const [loading, setLoading] = useState<boolean>(true);
    const [error, setError] = useState<string | null>(null);
    const [dataGridRows, setDataGridRows] = useState<any[]>([]);
    const [columns, setColumns] = useState<GridColDef[]>([]);
    const [isUseraddModalOpen, setIsUseraddModalOpen] = useState<boolean>(false);
    const [selectedNode, setSelectedNode] = useState<string>("");

    useEffect(() => {
        fetch('/demo/api/tree')
            .then(response => response.json())
            .then(jsonData => {
                setTreeData(jsonData);
                setLoading(false);
            })
            .catch(error => { console.error('Error fetching data:', error); });
    }, []);

    const handleNodeSelect = (node: UAMGroup) => {
        fetch(`/demo/api/users/${node.uid}?recursive=1`)
            .then(response => response.json())
            .then(data => {
                const dataWithID = data.map((row: UAMUser) => {
                    return {
                        name: row.name,
                        id: row.uid
                    }
                })
                setDataGridRows(dataWithID);
                setColumns([
                    { field: 'name', headerName: 'Name', width: 200 },
                    { field: 'date', headerName: 'Date', width: 150 },
                ]);
                setSelectedNode(node.name)
            })
            .catch(error => {
                console.error('Error fetching data:', error);
            });
    };


    // Recursive function to render tree items
    const renderTree = (nodes: UAMGroup) => (
        < TreeItem key={nodes.uid} itemId={nodes.uid} label={nodes.name} onClick={() => handleNodeSelect(nodes)}>
            {nodes.children.map((node: UAMGroup) => renderTree(node))}
        </TreeItem >
    );

    if (loading) {
        return <CircularProgress />;
    }

    const onOpenUserAddDialog = async () => {
        setIsUseraddModalOpen(true)
    }

    return (
        <Grid container spacing={2}>
            <Grid size={4} alignItems="left">
                {/* Info Field */}
                <Paper style={{
                    padding: '20px', display: 'flex',
                    flexDirection: 'column',
                }} sx={{ mt: 0, mb: 6 }}>
                    <Title>Group</Title>

                    <Typography variant="subtitle1" gutterBottom>
                        Group: {selectedNode}
                    </Typography>

                    <Grid container size="grow" spacing={2}>
                        <Grid>
                            <Button variant="contained" color="primary" disabled={true}
                                onClick={onOpenUserAddDialog}>Add User</Button>
                            <ShowAddUser isOpen={isUseraddModalOpen} setIsOpen={setIsUseraddModalOpen} />

                        </Grid>
                        <Grid>
                            <Button variant="contained" color="primary" disabled={true}
                                onClick={onOpenUserAddDialog}>Add Group</Button>
                            <ShowAddUser isOpen={isUseraddModalOpen} setIsOpen={setIsUseraddModalOpen} />

                        </Grid>
                    </Grid>
                </Paper>

                {/* TreeView section */}
                {loading ? (
                    <p>Loading...</p>
                ) : error ? (
                    <p>{error}</p>
                ) : (
                    <SimpleTreeView defaultSelectedItems={treeData.uid}>
                        {renderTree(treeData)}
                    </SimpleTreeView>
                )}

            </Grid>
            <Grid size={7} justifyContent="center" alignItems="center">
                <Paper style={{ padding: '20px', display: 'flex', flexDirection: 'column', }}>
                    <Title>Users in {selectedNode}</Title>
                    <Box height="70vh">
                        <DataGrid
                            disableColumnSelector
                            rows={dataGridRows}
                            columns={columns}
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
        </Grid>
    );
};
